from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.llm import generate_document,GenerationError,provider_call
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','mock')
    with TestClient(create_app('sqlite:///'+str(tmp_path/'test.db'))) as c:yield c

def upload(c,v):
    name='ct200_manual.pdf' if v=='v1' else 'ct200_manual_v2.pdf'
    return c.post('/versions/'+v,files={'file':(name,Path('data',name).read_bytes(),'application/pdf')})

def selection(c,key='2.1.1.1',name='battery'):
    r=c.post('/selections',json={'name':name,'version':'v1','node_ids':['v1:'+key]})
    assert r.status_code==201,r.text
    return r.json()['id']

def test_complete_version_flow(client):
    c=client
    assert upload(c,'v1').status_code==201
    assert len(c.get('/versions/v1/sections').json())==8
    assert c.get('/nodes/v1:2.1.1.1').json()['parent']=='2.1'
    sid=selection(c)
    g=c.post(f'/selections/{sid}/generate')
    assert g.status_code==201,g.text
    assert not g.json()['stale']
    assert len(g.json()['output']['cases'])==3
    unchanged=selection(c,'1.1','intended')
    c.post(f'/selections/{unchanged}/generate')
    assert upload(c,'v2').status_code==201
    stale=c.get('/generations',params={'stale':True}).json()
    assert len(stale)==1 and stale[0]['changed_source_keys']==['2.1.1.1']
    assert len(c.get('/generations',params={'stale':False}).json())==1
    assert len(c.get('/generations',params={'node_id':'v1:2.1.1.1'}).json())==1
    assert not c.get('/generations',params={'selection_id':sid,'against_version':'v1'}).json()[0]['stale']
    changes={x['key']:x for x in c.get('/diff',params={'from_version':'v1','to_version':'v2'}).json()}
    assert changes['5.3']['status']=='added'
    assert all(k in changes for k in ['2.1.1.1','3.2','4.2','4.3'])
    assert '1.1' not in changes
    assert c.get('/search',params={'version':'v2','q':'250 measurement'}).json()['total']==1

def test_validation_and_duplicates(client):
    c=client;upload(c,'v1')
    assert upload(c,'v1').status_code==409
    selection(c)
    assert c.post('/selections',json={'name':'battery','version':'v1','node_ids':['v1:1']}).status_code==409
    assert c.post('/selections',json={'name':'bad','version':'v1','node_ids':['v2:1']}).status_code==422
    assert c.get('/nodes/missing').status_code==404
    assert c.get('/diff',params={'from_version':'v1','to_version':'missing'}).status_code==404
    assert c.post('/versions/bad',files={'file':('bad.pdf',b'not pdf')}).status_code==422
    assert c.get('/search',params={'version':'v1','q':''}).status_code==422

def test_retry_and_exhaustion(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','mock')
    sources=[dict(id='v1:1',title='Test',full_text='The device stores 200 readings.')]
    calls=[]
    def retry(prompt,src):
        calls.append(1)
        return 'invalid' if len(calls)<3 else provider_call(prompt,src)
    assert len(generate_document(sources,retry)['attempts'])==3
    with pytest.raises(GenerationError):generate_document(sources,lambda *_:'{"cases":[]}')

def test_false_citation_rejected(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','mock')
    sources=[dict(id='v1:1',title='Test',full_text='The device stores 200 readings.')]
    raw=provider_call('',sources).replace('v1:1','v9:9')
    with pytest.raises(GenerationError):generate_document(sources,lambda *_:raw)

def test_live_missing_key_is_explicit(client,monkeypatch):
    upload(client,'v1');sid=selection(client)
    monkeypatch.setenv('LLM_PROVIDER','openai-compatible');monkeypatch.delenv('LLM_API_KEY',raising=False)
    assert client.post(f'/selections/{sid}/generate').status_code==502
    assert client.get('/generations').json()==[]

def test_provider_http_contract(monkeypatch):
    import httpx
    from app import llm
    monkeypatch.setenv('LLM_PROVIDER','openai-compatible')
    monkeypatch.setenv('LLM_API_KEY','test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://provider.example/v1')
    original=httpx.Client
    def handle(request):
        assert request.url.path=='/v1/chat/completions'
        assert request.headers['authorization']=='Bearer test-key'
        assert json.loads(request.content)['response_format']=={'type':'json_object'}
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"cases":[]}'}}]})
    monkeypatch.setattr(llm.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    assert llm.provider_call('test',[])=='{"cases":[]}'

def test_persistent_restart(tmp_path):
    url='sqlite:///'+str(tmp_path/'persistent.db')
    with TestClient(create_app(url)) as c:upload(c,'v1')
    with TestClient(create_app(url)) as c:
        assert c.get('/nodes/v1:4.2').status_code==200
        assert len(c.get('/versions').json())==1
