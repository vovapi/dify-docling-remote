import io
import json
import zipfile
import httpx
from dify_plugin import Tool
from engine.client import ServeClient, file_source, MAX_RESPONSE_BYTES, MAX_FILE_BYTES
from engine.options import parse, boolean
from engine.outputs import inline_outputs
from engine.errors import conversion_failure


class ConvertTool(Tool):
    def _invoke(self, tool_parameters):
        options, timeout, chunking, tokens = parse(tool_parameters)
        files = tool_parameters.get('files') or []
        if not isinstance(files, list):
            files = [files]
        if not 1 <= len(files) <= 10:
            raise ValueError('Provide 1–10 uploaded documents')
        # Dify file URLs expire. Cache every input before any long conversion.
        for file in files:
            try:
                blob = file.blob
            except (httpx.HTTPError, ValueError):
                raise RuntimeError('Could not download an input file from Dify; upload the files again and retry.') from None
            if not blob or len(blob) > MAX_FILE_BYTES:
                raise ValueError('Each document must be nonempty and at most 50 MiB')
        documents, texts = [], []
        archive = io.BytesIO()
        total = 0
        with ServeClient(self.runtime.credentials, timeout) as client, zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as exports:
            for index, file in enumerate(files):
                source = file_source(getattr(file, 'filename', None), file.blob)
                try:
                    result = client.convert(source, options, chunking, tokens)
                    status = result.get('status')
                    if status is None and chunking != 'none':
                        statuses = [d.get('status') for d in result.get('documents', [])]
                        status = 'success' if statuses and all(s == 'success' for s in statuses) else 'partial_success'
                    if status not in ('success', 'partial_success'):
                        raise RuntimeError(conversion_failure(result))
                    entry = {'filename': source['filename'], 'status': status, 'result': result}
                    data = json.dumps(result, ensure_ascii=False).encode()
                    total += len(data)
                    if total > MAX_RESPONSE_BYTES:
                        raise RuntimeError('Combined results exceed 100 MiB; reduce the batch')
                    exports.writestr(f'{index + 1}/result.json', data)
                    converted = [result['document']] if 'document' in result else [d['document'] for d in result.get('documents', []) if 'document' in d]
                    for j, doc in enumerate(converted):
                        text = doc.get('md_content') or doc.get('text_content')
                        if text:
                            texts.append(text)
                        for fmt, field in [('md', 'md_content'), ('text', 'text_content'), ('html', 'html_content'), ('doctags', 'doctags_content'), ('json', 'json_content')]:
                            content = doc.get(field)
                            if content is not None:
                                if not isinstance(content, str):
                                    content = json.dumps(content, ensure_ascii=False)
                                exports.writestr(f'{index + 1}/document-{j + 1}.{fmt}', content.encode())
                    documents.append(entry)
                except RuntimeError as exc:
                    if boolean(tool_parameters.get('fail_fast'), False):
                        raise
                    documents.append({'filename': source['filename'], 'status': 'failure', 'error': str(exc)})
        if not any(d['status'] != 'failure' for d in documents):
            raise RuntimeError(documents[0]['error'])
        inline_json, inline_text = inline_outputs(documents, texts)
        yield self.create_blob_message(archive.getvalue(), {'mime_type': 'application/zip', 'filename': 'docling-results.zip'})
        yield self.create_text_message(inline_text)
        yield self.create_json_message(inline_json)
