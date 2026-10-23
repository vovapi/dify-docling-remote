"""Bounded client for the stable Docling Serve v1 API."""
import base64
import json
import time
from urllib.parse import urlsplit, quote
from uuid import UUID

import httpx

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_RESPONSE_BYTES = 100 * 1024 * 1024


def base_url(value):
    value = str(value or '').strip().rstrip('/')
    try:
        parts = urlsplit(value)
        valid = parts.scheme in ('http', 'https') and parts.hostname and parts.port != 0
    except ValueError:
        valid = False
    if not valid or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Server URL must be HTTP(S), without credentials, query or fragment')
    return value


class ServeClient:
    def __init__(self, credentials, timeout=600, transport=None):
        self.url = base_url(credentials.get('server_url'))
        self.timeout = timeout
        key = credentials.get('api_key') or ''
        self.http = httpx.Client(headers={'X-Api-Key': key} if key else {},
                                 follow_redirects=False, trust_env=False,
                                 transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def request(self, method, path, deadline=None, **kwargs):
        remaining = deadline - time.monotonic() if deadline else 10
        if remaining <= 0:
            raise RuntimeError('Docling Serve deadline exceeded; server task may still be running')
        try:
            with self.http.stream(method, self.url + path, timeout=min(30, remaining), **kwargs) as response:
                if response.status_code >= 300:
                    # Server bodies may contain documents, URLs or secrets; do not relay them.
                    raise RuntimeError(f'Docling Serve returned HTTP {response.status_code}; check server configuration and logs')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise RuntimeError('Docling Serve response exceeds 100 MiB')
                    if deadline and time.monotonic() >= deadline:
                        raise RuntimeError('Docling Serve deadline exceeded')
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise ValueError('Expected JSON object')
                return result
        except httpx.TimeoutException:
            raise RuntimeError('Docling Serve request timed out; server task may still be running') from None
        except httpx.HTTPError:
            raise RuntimeError('Cannot connect to Docling Serve; verify URL, TLS and network access') from None
        except (ValueError, UnicodeError):
            raise RuntimeError('Docling Serve returned invalid JSON') from None

    def health(self):
        return self.request('GET', '/health')

    def convert(self, source, options, chunking='none', max_tokens=512):
        deadline = time.monotonic() + self.timeout
        options = dict(options)
        if chunking != 'none':
            options['to_formats'] = list(dict.fromkeys([*options.get('to_formats', ['md']), 'json']))
        result = self._job('/v1/convert/source/async',
                           {'sources': [source], 'target': {'kind': 'inbody'}, 'options': options}, deadline)
        if chunking == 'none' or result.get('status') not in ('success', 'partial_success'):
            return result
        document = result.get('document', {}).get('json_content')
        if not isinstance(document, dict):
            raise RuntimeError('Docling Serve did not return Docling JSON needed for chunking')
        # Chunk the converted JSON: PDF/OCR inference is not run a second time.
        encoded = base64.b64encode(json.dumps(document, ensure_ascii=False).encode()).decode('ascii')
        payload = {'sources': [{'kind': 'file', 'filename': 'converted.json', 'base64_string': encoded}],
                   'target': {'kind': 'inbody'}, 'include_converted_doc': False,
                   'convert_options': {'to_formats': ['json'], 'pdf_backend': options['pdf_backend'],
                                       'do_ocr': False},
                   'chunking_options': {'chunker': chunking, 'include_raw_text': True}}
        if chunking == 'hybrid':
            payload['chunking_options']['max_tokens'] = max_tokens
        chunk_result = self._job(f'/v1/chunk/{chunking}/source/async', payload, deadline)
        result['chunks'] = chunk_result.get('chunks', [])
        result['chunking_processing_time'] = chunk_result.get('processing_time')
        for chunk in result['chunks']:
            chunk['filename'] = source.get('filename', 'document')
        return result

    def _job(self, path, payload, deadline):
        task = self.request('POST', path, deadline, json=payload)
        task_id = task.get('task_id')
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError('Docling Serve did not return a task ID')
        task_id = quote(task_id, safe='')
        while task.get('task_status') not in ('success', 'partial_success'):
            if task.get('task_status') in ('failure', 'skipped', 'cancelled'):
                stage = 'chunking' if path.startswith('/v1/chunk/') else 'conversion'
                try:
                    reference = f' (task {UUID(task_id)})'
                except ValueError:
                    reference = ''
                # Only fixed hints are exposed, never arbitrary server error text.
                detail = str(task.get('error_message') or '').lower()
                hint = 'Check server logs for this task.'
                if 'unexpected pdf backend' in detail:
                    hint = 'Select PDF backend pypdfium2; check Serve/Jobkit compatibility.'
                elif 'rapidocr' in detail and ('artifact' in detail or 'not found' in detail):
                    hint = 'RapidOCR weights are unavailable; provision them or select an installed OCR engine.'
                elif 'easyocr' in detail and ('not found' in detail or 'download' in detail or 'missing' in detail):
                    hint = 'Check EasyOCR installation and language weights on Serve.'
                elif 'tokenizer' in detail:
                    hint = 'Check the server tokenizer and its offline cache; try hierarchical chunking.'
                raise RuntimeError(f'Docling Serve task failed during {stage}{reference}. {hint}')
            if time.monotonic() >= deadline:
                raise RuntimeError('Docling Serve deadline exceeded; server task may still be running')
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            task = self.request('GET', f'/v1/status/poll/{task_id}', deadline, params={'wait': 1})
        result = self.request('GET', f'/v1/result/{task_id}', deadline)
        try:
            result['task_id'] = str(UUID(task_id))
        except ValueError:
            pass
        return result


def file_source(name, blob):
    if not blob or len(blob) > MAX_FILE_BYTES:
        raise ValueError('Each document must be nonempty and at most 50 MiB')
    name = str(name or 'document').replace('\\', '/').split('/')[-1].replace('\x00', '')[:180] or 'document'
    return {'kind': 'file', 'filename': name, 'base64_string': base64.b64encode(blob).decode('ascii')}
