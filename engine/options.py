import math


def integer(value, default, low, high, name):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        raise ValueError(f'{name} must be an integer')
    try:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer() or not low <= number <= high:
            raise ValueError
        return int(number)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be an integer between {low} and {high}') from None


def boolean(value, default):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value in ('true', 'false'):
        return value == 'true'
    raise ValueError('Boolean option must be true or false')


def choice(value, default, allowed):
    value = value or default
    if value not in allowed:
        raise ValueError(f'Expected one of: {", ".join(allowed)}')
    return value


def parse(parameters):
    formats = list(dict.fromkeys(x.strip() for x in str(parameters.get('output_formats') or 'md,json').split(',') if x.strip()))
    if not formats or set(formats) - {'md', 'json', 'html', 'text', 'doctags'}:
        raise ValueError('Output formats: md,json,html,text,doctags')
    options = {'to_formats': formats, 'image_export_mode': 'embedded',
               'pdf_backend': choice(parameters.get('pdf_backend'), 'pypdfium2', ('pypdfium2', 'docling_parse')),
               'pipeline': choice(parameters.get('pipeline'), 'standard', ('standard', 'vlm')),
               'ocr_engine': choice(parameters.get('ocr_engine'), 'auto', ('auto', 'easyocr', 'rapidocr', 'tesseract')),
               'table_mode': choice(parameters.get('table_mode'), 'accurate', ('accurate', 'fast'))}
    for name, default in [('do_ocr', True), ('force_ocr', False), ('do_table_structure', True),
                          ('do_code_enrichment', False), ('do_formula_enrichment', False),
                          ('do_picture_classification', False), ('do_picture_description', False),
                          ('include_page_images', False)]:
        options[name] = boolean(parameters.get(name), default)
    languages = str(parameters.get('ocr_languages') or '').strip()
    if languages:
        options['ocr_lang'] = [x.strip() for x in languages.split(',') if x.strip()]
    first = integer(parameters.get('first_page'), 1, 1, 100000, 'First page')
    last = integer(parameters.get('last_page'), 100000, first, 100000, 'Last page')
    options['page_range'] = [first, last]
    timeout = integer(parameters.get('timeout'), 600, 10, 7000, 'Timeout')
    options['document_timeout'] = timeout
    chunking = choice(parameters.get('chunking'), 'none', ('none', 'hierarchical', 'hybrid'))
    tokens = integer(parameters.get('max_tokens'), 512, 32, 32768, 'Max tokens')
    return options, timeout, chunking, tokens
