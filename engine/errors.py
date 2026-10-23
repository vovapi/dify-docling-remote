"""Fixed diagnostic hints; never include arbitrary server messages or paths."""
from uuid import UUID


def conversion_failure(result):
    status = result.get('status')
    if status not in ('failure', 'skipped', 'partial_success', 'pending', 'started', 'success'):
        status = 'invalid response'
    errors = result.get('errors')
    errors = errors if isinstance(errors, list) else []
    details = ' '.join(str(e.get('error_message', '')) for e in errors if isinstance(e, dict)).lower()
    hint = 'Check server logs for the task.'
    if any(word in details for word in ('timeout', 'timed out', 'time limit')):
        hint = 'The server reported a document timeout; disable full-page OCR for text PDFs or process fewer pages.'
    elif 'page' in details and any(word in details for word in ('limit', 'maximum', 'exceed')):
        hint = 'The server reported a page limit; reduce the page range or ask the Serve administrator to check its limits.'
    elif any(word in details for word in ('encrypted', 'password')):
        hint = 'The server could not open a protected PDF; provide an unlocked copy.'
    elif 'backend' in details or 'pdfium' in details:
        hint = 'Check PDF parser compatibility; try the other PDF backend or a smaller page range.'
    elif any(word in details for word in ('out of memory', 'memoryerror', 'cuda error')):
        hint = 'The server reported a resource error; reduce pages and image generation.'
    reference = ''
    try:
        reference = f'; task={UUID(str(result.get("task_id", "")))}'
    except ValueError:
        pass
    return f'Document conversion failed (status={status}; errors={len(errors)}{reference}). {hint}'
