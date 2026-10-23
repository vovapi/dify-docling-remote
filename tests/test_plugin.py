import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import dify_plugin  # SDK initializes gevent before networking imports.
import httpx
import pytest
import yaml
from dify_plugin.core.entities.plugin.setup import PluginConfiguration
from dify_plugin.entities.tool import ToolConfiguration, ToolProviderConfiguration, ToolRuntime
from engine.client import ServeClient, base_url, file_source
from engine.options import parse
from tools.convert import ConvertTool


def test_sdk_schemas():
    PluginConfiguration.model_validate(yaml.safe_load(Path('manifest.yaml').read_text()))
    ToolProviderConfiguration.model_validate(yaml.safe_load(Path('provider/docling.yaml').read_text()))
    for path in Path('tools').glob('*.yaml'):
        ToolConfiguration.model_validate(yaml.safe_load(path.read_text()))


@pytest.mark.parametrize('url', ['file:///etc/passwd','http://user:secret@host','http://host/?key=secret','http://host/#secret','http://host:bad'])
def test_bad_urls(url):
    with pytest.raises(ValueError):
        base_url(url)


def test_internal_server_and_source():
    assert base_url('http://docling-serve:5001/') == 'http://docling-serve:5001'
    assert file_source('../../a.html', b'hello')['filename'] == 'a.html'
    with pytest.raises(ValueError):
        file_source('a', b'')


@pytest.mark.parametrize('parameters', [{'timeout':True},{'timeout':float('nan')},{'first_page':5,'last_page':2},{'chunking':'shell'},{'output_formats':'zip'},{'do_ocr':'yes'}])
def test_invalid_options(parameters):
    with pytest.raises(ValueError):
        parse(parameters)


def test_async_contract(monkeypatch):
    monkeypatch.setattr('engine.client.time.sleep', lambda _:None)
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        assert request.headers['X-Api-Key']=='secret'
        if request.method=='POST':
            body=json.loads(request.content)
            assert body['target']=={'kind':'inbody'}
            assert body['sources'][0]['kind']=='file'
            assert body['chunking_options']['chunker']=='hierarchical'
            return httpx.Response(200,json={'task_id':'abc','task_status':'pending'})
        if '/poll/' in request.url.path:
            return httpx.Response(200,json={'task_status':'success'})
        return httpx.Response(200,json={'chunks':[],'documents':[]})
    with ServeClient({'server_url':'http://serve','api_key':'secret'},transport=httpx.MockTransport(handler)) as client:
        assert client._job('/v1/chunk/hierarchical/source/async', {'sources':[file_source('a.html',b'hello')], 'target':{'kind':'inbody'}, 'chunking_options':{'chunker':'hierarchical'}}, __import__('time').monotonic()+10)['chunks']==[]
    assert paths==['/v1/chunk/hierarchical/source/async','/v1/status/poll/abc','/v1/result/abc']


@pytest.mark.parametrize('status',[302,401,422,500])
def test_errors_redacted(status):
    with ServeClient({'server_url':'http://serve','api_key':'secret'},transport=httpx.MockTransport(lambda _:httpx.Response(status,text='secret document'))) as client:
        with pytest.raises(RuntimeError) as error:
            client.health()
        assert 'secret' not in str(error.value)


def test_actual_sdk_messages_and_partial_failure(monkeypatch):
    def convert(self, source, *args):
        if source['filename']=='bad.pdf':raise RuntimeError('Conversion failed')
        return {'status':'success','document':{'md_content':'Привет 中文 العربية','json_content':{'name':'Test'}}}
    monkeypatch.setattr(ServeClient,'convert',convert)
    tool=ConvertTool(ToolRuntime(credentials={'server_url':'http://serve'},user_id=None,session_id=None),None)
    messages=list(tool._invoke({'files':[SimpleNamespace(filename='bad.pdf',blob=b'bad'),SimpleNamespace(filename='good.html',blob=b'good')]}))
    assert [m.type.value for m in messages]==['blob','text','json']
    assert 'Привет' in messages[1].message.text
    assert [d['status'] for d in messages[2].message.json_object['documents']]==['failure','success']
    with zipfile.ZipFile(io.BytesIO(messages[0].message.blob)) as archive:
        assert '2/document-1.md' in archive.namelist()


def test_invalid_json_and_limit(monkeypatch):
    for response in [httpx.Response(200,text='not JSON'),httpx.Response(200,json=[])]:
        with ServeClient({'server_url':'http://serve'},transport=httpx.MockTransport(lambda _,r=response:r)) as client:
            with pytest.raises(RuntimeError,match='invalid JSON'):client.health()
    monkeypatch.setattr('engine.client.MAX_RESPONSE_BYTES',4)
    with ServeClient({'server_url':'http://serve'},transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'large':'data'}))) as client:
        with pytest.raises(RuntimeError,match='exceeds'):client.health()


def test_task_failure_and_deadline(monkeypatch):
    monkeypatch.setattr('engine.client.time.sleep',lambda _:None)
    with ServeClient({'server_url':'http://serve'},transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'task_id':'a','task_status':'failure','error_message':'secret'}))) as client:
        with pytest.raises(RuntimeError,match='task failed') as error:client.convert(file_source('a',b'a'),{})
        assert 'secret' not in str(error.value)
    with ServeClient({'server_url':'http://serve'},timeout=0,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={}))) as client:
        with pytest.raises(RuntimeError,match='deadline exceeded'):client.convert(file_source('a',b'a'),{})


def test_all_failed_and_fail_fast(monkeypatch):
    calls=[]
    def fail(self,source,*args):
        calls.append(source['filename']);raise RuntimeError('Server failed')
    monkeypatch.setattr(ServeClient,'convert',fail)
    tool=ConvertTool(ToolRuntime(credentials={'server_url':'http://serve'},user_id=None,session_id=None),None)
    files=[SimpleNamespace(filename='1.pdf',blob=b'a'),SimpleNamespace(filename='2.pdf',blob=b'b')]
    with pytest.raises(RuntimeError,match='Server failed'):list(tool._invoke({'files':files}))
    assert len(calls)==2
    calls.clear()
    with pytest.raises(RuntimeError,match='Server failed'):list(tool._invoke({'files':files,'fail_fast':True}))
    assert len(calls)==1


def test_chunking_reuses_converted_json(monkeypatch):
    jobs=[]
    def job(self,path,payload,deadline):
        jobs.append((path,payload,deadline))
        if 'convert/source' in path:
            assert 'json' in payload['options']['to_formats']
            return {'status':'success','document':{'md_content':'Hello','json_content':{'name':'converted'}}}
        assert payload['sources'][0]['filename']=='converted.json'
        assert payload['convert_options']['do_ocr'] is False
        return {'chunks':[{'text':'Hello','filename':'converted.json'}]}
    monkeypatch.setattr(ServeClient,'_job',job)
    with ServeClient({'server_url':'http://serve'}) as client:
        result=client.convert(file_source('original.pdf',b'pdf'),{'to_formats':['md'],'pdf_backend':'pypdfium2'},'hierarchical')
    assert result['document']['md_content']=='Hello'
    assert result['chunks'][0]['filename']=='original.pdf'
    assert jobs[0][2]==jobs[1][2]


def test_embedded_images_only_in_zip(monkeypatch):
    from engine.outputs import inline_outputs
    uri='data:image/png;base64,'+'A'*6_000_000
    raw=[{'filename':'scan.pdf','status':'success','result':{'document':{'json_content':{'pages':{'1':{'image':{'uri':uri,'size':{'width':10,'height':10}}}}},'html_content':f'<img src="{uri}">'},'chunks':[{'text':'Привет'}]}}]
    inline,text=inline_outputs(raw,['Привет'])
    assert raw[0]['result']['document']['json_content']['pages']['1']['image']['uri']==uri
    item=inline['documents'][0]
    assert item['embedded_images_in_zip'] is True
    assert item['result']['document']['json_content']['pages']['1']['image'] is None
    assert item['result']['chunks'][0]['text']=='Привет'
    assert len(json.dumps(inline))<1000
    assert text=='Привет'


def test_oversized_inline_outputs_have_archive_fallback(monkeypatch):
    from engine.outputs import inline_outputs
    monkeypatch.setattr('engine.outputs.MAX_INLINE_JSON',100)
    monkeypatch.setattr('engine.outputs.MAX_INLINE_TEXT',10)
    raw=[{'filename':'large.pdf','status':'success','result':{'text':'x'*1000}}]
    inline,text=inline_outputs(raw,['a'*30])
    assert inline['documents'][0]['full_result_in_zip']=='1/result.json'
    assert 'Text truncated' in text


@pytest.mark.parametrize('path,detail,expected',[
 ('/v1/convert/source/async','Unexpected PDF backend type token=secret','pypdfium2'),
 ('/v1/convert/source/async','RapidOCR artifacts not found /private/secret','RapidOCR weights'),
 ('/v1/chunk/hybrid/source/async','tokenizer failed token=secret','hierarchical'),
 ('/v1/convert/source/async','private document secret','Check server logs'),
])
def test_safe_failure_diagnostics(path,detail,expected):
    import time
    task_id='d49b25ee-582f-48a1-af19-ab7886b0738f'
    transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'task_id':task_id,'task_status':'failure','error_message':detail}))
    with ServeClient({'server_url':'http://serve'},transport=transport) as client:
        with pytest.raises(RuntimeError) as error:client._job(path,{},time.monotonic()+10)
    assert expected in str(error.value)
    assert task_id in str(error.value)
    assert ('chunking' if '/chunk/' in path else 'conversion') in str(error.value)
    assert 'secret' not in str(error.value)


def test_large_structure_keeps_complete_per_file_text(monkeypatch):
    from engine.outputs import inline_outputs
    monkeypatch.setattr('engine.outputs.MAX_INLINE_JSON',2000)
    raw=[{'filename':'thesis.pdf','status':'success','result':{'document':{'md_content':'Complete document text','json_content':{'large':'x'*5000}}}}]
    inline,_=inline_outputs(raw,['Complete document text'])
    document=inline['documents'][0]
    assert document['result']['document']['md_content']=='Complete document text'
    assert document['full_result_in_zip']=='1/result.json'
    assert document['inline_result_summarized'] is True
    assert 'large' in raw[0]['result']['document']['json_content']


def test_conversion_failure_diagnostics_do_not_leak():
    from engine.errors import conversion_failure
    result={'status':'failure','task_id':'d49b25ee-582f-48a1-af19-ab7886b0738f','errors':[{'error_message':'timeout secret-key /private/document'}]}
    error=conversion_failure(result)
    assert 'document timeout' in error
    assert 'errors=1' in error
    assert result['task_id'] in error
    assert 'secret' not in error and '/private' not in error


def test_download_all_inputs_before_conversion(monkeypatch):
    events = []
    class Input:
        filename = 'input.pdf'
        @property
        def blob(self):
            events.append('download')
            return b'pdf'
    def convert(self, *args):
        events.append('convert')
        assert events[:2] == ['download', 'download']
        return {'status': 'success', 'document': {'md_content': 'text'}}
    monkeypatch.setattr(ServeClient, 'convert', convert)
    tool = ConvertTool(ToolRuntime(credentials={'server_url': 'http://serve'}, user_id=None, session_id=None), None)
    list(tool._invoke({'files': [Input(), Input()]}))


def test_input_download_error_is_redacted():
    class Input:
        @property
        def blob(self):
            raise httpx.HTTPStatusError('secret signed URL', request=httpx.Request('GET', 'http://dify'), response=httpx.Response(404))
    tool = ConvertTool(ToolRuntime(credentials={'server_url': 'http://serve'}, user_id=None, session_id=None), None)
    with pytest.raises(RuntimeError, match='upload the files again') as exc:
        list(tool._invoke({'files': [Input()]}))
    assert 'secret' not in str(exc.value)
