"""Reproducible v1 -> generation -> v2 -> stale demonstration, no server needed."""
import json,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
with tempfile.TemporaryDirectory() as tmp:
    with TestClient(create_app('sqlite:///'+str(Path(tmp)/'demo.db'))) as c:
        def upload(v,name):
            r=c.post('/versions/'+v,files={'file':(name,Path('data',name).read_bytes(),'application/pdf')})
            r.raise_for_status();return r.json()
        v1=upload('v1','ct200_manual.pdf')
        sel=c.post('/selections',json={'name':'Battery regression','version':'v1','node_ids':['v1:2.1.1.1']}).json()
        generated=c.post('/selections/'+sel['id']+'/generate');generated.raise_for_status()
        v2=upload('v2','ct200_manual_v2.pdf')
        report={'v1':v1,'v2':v2,'generation_before_update':generated.json(),'stale_after_update':c.get('/generations',params={'stale':True}).json(),'diff':c.get('/diff',params={'from_version':'v1','to_version':'v2'}).json()}
        Path('docs/demo-results.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'v1_nodes':v1['nodes'],'v2_nodes':v2['nodes'],'stale_generations':len(report['stale_after_update']),'changed_keys':[x['key'] for x in report['diff']]},indent=2))
