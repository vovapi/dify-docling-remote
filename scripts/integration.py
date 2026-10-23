"""Opt-in real Serve smoke test; server URL/key are environment variables."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

from dify_plugin.entities.tool import ToolRuntime
from tools.convert import ConvertTool


def main():
    credentials={'server_url':os.environ['DOCLING_TEST_URL'],'api_key':os.getenv('DOCLING_TEST_API_KEY','')}
    tool=ConvertTool(ToolRuntime(credentials=credentials,user_id=None,session_id=None),None)
    html='<html><body><h1>Пример Example</h1><p>Русский English 中文 العربية</p><table><tr><th>Name</th><th>Value</th></tr><tr><td>Тест</td><td>42</td></tr></table></body></html>'.encode()
    parameters={'files':[SimpleNamespace(filename='sample.html',blob=html)],'output_formats':'md,json,text,html,doctags','chunking':'hierarchical','ocr_engine':'easyocr','ocr_languages':'ru,en'}
    scan=os.getenv('DOCLING_TEST_SCAN')
    if scan:
        parameters.update(files=[SimpleNamespace(filename='scan.pdf',blob=Path(scan).read_bytes())],ocr_engine='easyocr',ocr_languages='ru,en',force_ocr=True,include_page_images=True)
    messages=list(tool._invoke(parameters))
    assert [m.type.value for m in messages]==['blob','text','json']
    text=messages[1].message.text
    assert all(value in text for value in (['12345', 'русском'] if scan else ['Русский', '中文', 'العربية']))
    result=messages[2].message.json_object['documents'][0]['result']
    assert result['chunks']
    if scan:
        assert result['chunks'][0]['page_numbers'] == [1]
    else:
        assert len(result['document']['json_content']['tables']) == 1
    with zipfile.ZipFile(io.BytesIO(messages[0].message.blob)) as archive:
        if scan:
            assert json.loads(archive.read('1/document-1.json'))['pages']['1']['image']
        assert {'1/document-1.md','1/document-1.json','1/document-1.text','1/document-1.html','1/document-1.doctags'} <= set(archive.namelist())
    print(json.dumps({'status':'passed','kind':'OCR' if scan else 'HTML','chunks':len(result['chunks']),'zip_bytes':len(messages[0].message.blob)},ensure_ascii=False))


if __name__=='__main__':main()
