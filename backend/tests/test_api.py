import io
import json
import zipfile
import pytest
from PIL import Image

XML='<annotations><image name="a.png" width="100" height="100"><box label="car" xtl="1" ytl="2" xbr="30" ybr="40"/></image><image name="b.png" width="100" height="100"><points label="pose" points="1,1;3,3"/></image></annotations>'

def upload(client,xml=XML):
    return client.post('/api/datasets/upload',data={'name':'Real import fixture'},files=[('annotations',('labels.xml',xml,'application/xml'))])

def test_health_and_empty_database(client):
    assert client.get('/api/health').json()['status']=='ok'
    assert client.get('/api/datasets').json()==[]
    assert client.get('/docs').status_code==200

def test_connected_workflow_and_persistence(client):
    response=upload(client);assert response.status_code==200,response.text
    d=response.json();id=d['id'];assert d['task_type']=='MIXED' and d['sample_count']==2
    samples=client.get(f'/api/datasets/{id}/samples').json()
    assert all(s['visual_difficulty'] is None for s in samples)
    detail=client.get(f"/api/samples/{samples[0]['id']}").json()
    assert detail['annotations'][0]['shape_type']=='BBOX_2D'
    assert client.post(f'/api/datasets/{id}/balance').status_code==422
    run=client.post(f'/api/datasets/{id}/sampling',json={'mode':'count','budget':2}).json();assert len(run['selections'])==2
    reviewer=client.post(f'/api/datasets/{id}/reviewers',json={'name':'Actual reviewer'}).json()
    rows=client.post(f'/api/datasets/{id}/balance').json();assert len(rows)==2
    a=rows[0]['assignment_id']
    saved=client.put(f'/api/assignments/{a}/review',json={'status':'ISSUE_FOUND','note':'Human finding'}).json()
    assert saved['status']=='ISSUE_FOUND'
    queue=client.get(f"/api/reviewers/{reviewer['id']}/queue").json()
    assert any(x['note']=='Human finding' for x in queue)
    assert queue[0]['overall_difficulty']>=queue[1]['overall_difficulty']
    assert client.delete(f"/api/reviewers/{reviewer['id']}").status_code==409
    assert client.post(f'/api/datasets/{id}/balance').status_code==409
    for kind in ('smart_sample','review_assignments','review_results'):
        export=client.get(f'/api/datasets/{id}/exports/{kind}');assert export.status_code==200
        assert 'sample_id' in export.text
    config=client.get('/api/settings').json()
    assert client.put('/api/settings',json=config).status_code==200
    assert client.get(f'/api/datasets/{id}/sampling').json()['needs_regeneration']
    assert client.post(f'/api/datasets/{id}/balance').status_code==409
    client.post(f'/api/datasets/{id}/sampling',json={'mode':'count','budget':1})
    assert 'Human finding' in client.get(f'/api/datasets/{id}/exports/review_results').text
    assert client.delete(f'/api/datasets/{id}').status_code==200
    assert client.get('/api/datasets').json()==[]

def test_image_upload_matching_and_scoring(client):
    image=io.BytesIO();Image.new('RGB',(100,100),(120,120,120)).save(image,format='PNG')
    response=client.post('/api/datasets/upload',data={'name':'image test'},files=[('annotations',('a.xml',XML)),('media',('a.png',image.getvalue(),'image/png'))])
    assert response.status_code==200,response.text
    rows=client.get(f"/api/datasets/{response.json()['id']}/samples").json()
    assert rows[0]['visual_difficulty'] is not None
    assert client.get(rows[0]['media_url']).status_code==200

def test_malformed_and_unsupported_upload(client):
    assert upload(client,'<broken').status_code==422
    assert upload(client,'<annotations/>').status_code==422
    assert client.post('/api/datasets/upload',data={'name':'x','format':'BAD'},files={'annotations':('a.txt','text')}).status_code==422
    assert client.get('/api/datasets').json()==[]

def test_browser_empty_optional_media_field(client):
    response=client.post('/api/datasets/upload',data={'name':'no media'},files=[('annotations',('labels.xml',XML)),('media',('',b''))])
    assert response.status_code==200,response.text

def test_zip_traversal_rejected(client):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive: archive.writestr('../escape.xml',XML)
    response=client.post('/api/datasets/upload',data={'name':'unsafe'},files={'annotations':('a.zip',data.getvalue())})
    assert response.status_code==422 and 'Unsafe ZIP' in response.text

def test_zip_success_and_invalid_budget(client):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive: archive.writestr('nested/labels.xml',XML)
    response=client.post('/api/datasets/upload',data={'name':'archive'},files={'annotations':('a.zip',data.getvalue())})
    assert response.status_code==200,response.text
    id=response.json()['id']
    assert client.post(f'/api/datasets/{id}/sampling',json={'budget':101}).status_code==422
    assert client.post(f'/api/datasets/{id}/sampling',json={'mode':'count','budget':1.5}).status_code==422
    assert client.post(f'/api/datasets/{id}/sampling',json={'weights':{'random':.3,'difficulty':.3,'edge':.3}}).status_code==422

def test_class_rarity_dataset_level(client):
    xml='<annotations><image name="a" width="100" height="100">'+''.join(f'<box label="{label}" xtl="1" ytl="1" xbr="10" ybr="10"/>' for label in ['common']*20+['rare'])+'</image></annotations>'
    d=upload(client,xml).json()
    assert d['rare_classes']==['rare']

@pytest.mark.parametrize('format,filename,content,expected',[
    ('COCO','labels.json',json.dumps({'images':[{'id':1,'file_name':'a.png','width':100,'height':100}],'categories':[{'id':1,'name':'car'}],'annotations':[{'id':1,'image_id':1,'category_id':1,'bbox':[1,1,20,20]}]}),'BBOX_2D'),
    ('YOLO','a.txt','0 0.5 0.5 0.2 0.2','BBOX_2D'),
    ('KITTI','a.txt','Car 0.1 1 0 0 0 10 10 1.5 1.8 4 1 2 30 0.5','CUBOID_3D'),
])
def test_other_formats_through_upload_analysis(client,format,filename,content,expected):
    image=io.BytesIO();Image.new('RGB',(100,100),(120,120,120)).save(image,format='PNG')
    response=client.post('/api/datasets/upload',data={'name':format,'format':format},files=[('annotations',(filename,content)),('media',('a.png',image.getvalue(),'image/png'))])
    assert response.status_code==200,response.text
    d=response.json();assert d['task_type']==expected and d['annotation_count']==1
    rows=client.get(f"/api/datasets/{d['id']}/samples").json()
    assert 0<=rows[0]['overall_difficulty']<=100
    detail=client.get(f"/api/samples/{rows[0]['id']}").json()
    assert sum(detail['analysis']['feature_contributions'].values())==pytest.approx(rows[0]['overall_difficulty'],abs=.002)
