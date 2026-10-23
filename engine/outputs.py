"""Keep native Dify protocol messages below the daemon's stdio line limit."""
import json
import re

MAX_INLINE_JSON = 2 * 1024 * 1024
MAX_INLINE_TEXT = 256 * 1024
DATA_IMAGE = re.compile(r'data:image/[a-zA-Z0-9.+-]+;base64,[a-zA-Z0-9+/=\r\n]+')


def without_images(value):
    if isinstance(value, dict):
        return {key: (None if key == 'image' and isinstance(item, dict)
                     and str(item.get('uri', '')).startswith('data:image/') else without_images(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [without_images(item) for item in value]
    if isinstance(value, str):
        return DATA_IMAGE.sub('about:blank#image-in-zip', value)
    return value


def inline_outputs(documents, texts):
    compact = without_images(documents)
    for item, original in zip(compact, documents):
        if item != original:
            item['embedded_images_in_zip'] = True
    output = {'documents': compact}
    # SDK serializes Unicode escapes; measure that representation, not just UTF-8.
    if len(json.dumps(output).encode()) > MAX_INLINE_JSON:
        summaries = []
        for index, item in enumerate(compact):
            summary = {key: item[key] for key in ('filename', 'status', 'error') if key in item}
            summary['full_result_in_zip'] = f'{index + 1}/result.json'
            document = item.get('result', {}).get('document', {})
            markdown = document.get('md_content') or document.get('text_content')
            if markdown:
                summary['result'] = {'document': {'filename': item['filename'], 'md_content': markdown}}
                summary['inline_result_summarized'] = True
            summaries.append(summary)
        output = {'documents': summaries}
        if len(json.dumps(output).encode()) > MAX_INLINE_JSON:
            for summary in summaries:
                if summary.pop('result', None) is not None:
                    summary['inline_text_omitted'] = True
    text = '\n\n---\n\n'.join(without_images(texts))
    if len(text) > MAX_INLINE_TEXT:
        text = text[:MAX_INLINE_TEXT] + '\n\n[Text truncated for Dify; full exports are in the ZIP.]'
    return output, text
