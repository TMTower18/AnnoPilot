from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from app.analyzers import area,iou,polygon_area,combine,feature,image_analysis,analyze_sample,BBoxDifficultyAnalyzer,SegmentationDifficultyAnalyzer,KeypointDifficultyAnalyzer,Cuboid3DDifficultyAnalyzer
from app.schemas import ScoringSettings,SamplingRequest
from app.services.pipeline import choose_samples,balance

SETTINGS=ScoringSettings()
def annotation(kind='BBOX_2D',geometry=None,label='car',occluded=None,metadata=None):
    return NS(shape_type=kind,geometry=geometry or dict(x1=0,y1=0,x2=5,y2=5),label=label,occluded=occluded,source_metadata=metadata or {})
def sample(id=1,score=None,annotations=None):
    return NS(id=id,annotations=annotations or [],width=100,height=100,media_path=None,analysis=NS(overall_difficulty=score,details={'per_type':{},'visual':{'features':{}}}))

def test_geometry_metrics():
    a=dict(x1=0,y1=0,x2=10,y2=10);b=dict(x1=5,y1=0,x2=15,y2=10)
    assert area(a)==100
    assert iou(a,b)==pytest.approx(1/3)
    assert polygon_area([[0,0],[10,0],[0,10]])==50

def test_unavailable_weight_renormalization():
    score,c=combine({'a':feature(.5),'b':feature(reason='missing'),'c':feature(1)},dict(a=.4,b=.3,c=.3))
    assert score==pytest.approx(71.4286)
    assert 'b' not in c
    assert combine({'a':feature(reason='missing')},{'a':1})==(None,{})

def test_bbox_tiny_unique_overlap_rare():
    a=[annotation(),annotation(occluded=True)]
    f=BBoxDifficultyAnalyzer().features(a,100,100,{'car'},SETTINGS)
    assert f['tiny']['raw']==2
    assert f['overlap']['raw']['pairs']==1
    assert f['rare']['value']==1
    assert f['occlusion']['value']==1

def test_no_dimensions_is_unavailable():
    f=BBoxDifficultyAnalyzer().features([annotation()],None,None,set(),SETTINGS)
    assert not f['tiny']['available']
    assert not f['occlusion']['available']

def test_segmentation_complexity():
    a=annotation('POLYGON',{'points':[[0,0],[10,0],[0,10]]})
    f=SegmentationDifficultyAnalyzer().features([a],100,100,set(),SETTINGS)
    assert f['complexity']['raw']['vertices']==3
    assert f['tiny']['value']==1

def test_keypoint_visibility():
    a=annotation('KEYPOINT',{'points':[dict(x=1,y=1,visibility=0),dict(x=2,y=2,visibility=1),dict(x=3,y=3,visibility=2)]})
    f=KeypointDifficultyAnalyzer().features([a],100,100,set(),SETTINGS)
    assert f['missing']['value']==pytest.approx(1/3,abs=1e-6)
    assert f['occlusion']['value']==pytest.approx(1/3,abs=1e-6)
    a.geometry={'points':[dict(x=1,y=2)]}
    assert not KeypointDifficultyAnalyzer().features([a],100,100,set(),SETTINGS)['missing']['available']

def test_cuboid_sensor_features_unavailable():
    a=annotation('CUBOID_3D',{'position':dict(x=0,y=0,z=10),'dimensions':dict(length=4,width=2,height=2),'rotation':{'yaw':0}})
    f=Cuboid3DDifficultyAnalyzer().features([a],None,None,set(),SETTINGS)
    assert not f['sparsity']['available'] and not f['distance_to_sensor']['available']

def test_visual_metrics_and_blur(tmp_path):
    rng=np.random.default_rng(42);sharp=rng.integers(0,256,(100,100),dtype=np.uint8)
    p=tmp_path/'sharp.png';q=tmp_path/'blur.png';cv2.imwrite(str(p),sharp);cv2.imwrite(str(q),cv2.GaussianBlur(sharp,(15,15),5))
    a=image_analysis(p,SETTINGS);b=image_analysis(q,SETTINGS)
    assert b['features']['blur']['value']>a['features']['blur']['value']
    assert set(a['features'])=={'blur','exposure','low_contrast','edge_complexity','entropy'}
    assert 0<=a['score']<=100
    dark=tmp_path/'dark.png';cv2.imwrite(str(dark),np.zeros((20,20),np.uint8))
    d=image_analysis(dark,SETTINGS)
    assert d['features']['exposure']['value']==1
    assert d['features']['entropy']['raw']==0
    assert d['features']['low_contrast']['value']==1

def test_missing_media_overall_deterministic_and_contributions():
    s=sample(annotations=[annotation()]);a=analyze_sample(s,set(),SETTINGS)
    assert a==analyze_sample(s,set(),SETTINGS)
    assert a['visual_difficulty'] is None
    assert a['overall_difficulty']==a['annotation_difficulty']
    assert 0<=a['overall_difficulty']<=100
    assert sum(a['details']['feature_contributions'].values())==pytest.approx(a['overall_difficulty'],abs=.002)

def test_mixed_types_count_weighted():
    s=sample(annotations=[annotation(),annotation('KEYPOINT',{'points':[dict(x=1,y=1)]})])
    result=analyze_sample(s,set(),SETTINGS)
    scores=[v['score'] for v in result['details']['per_type'].values()]
    assert result['annotation_difficulty']==pytest.approx(sum(scores)/2,abs=.001)

@pytest.mark.parametrize('budget',[1,10,100,150])
def test_sampling_budget_no_duplicates_and_determinism(budget):
    samples=[sample(i,i*5) for i in range(20)]
    config=SamplingRequest(mode='count',budget=budget)
    selected=choose_samples(samples,config)
    assert len(selected)==min(budget,len(samples))
    assert selected==choose_samples(samples,config)

def test_balance_deterministic_and_effort():
    samples=[sample(i,v) for i,v in enumerate([90,80,70,20,10])]
    reviewers=[NS(id=1),NS(id=2)]
    result=balance(samples,reviewers)
    assert result==balance(samples,reviewers)
    loads={r.id:sum(s.analysis.overall_difficulty for s in samples if result[s.id]==r.id) for r in reviewers}
    # Greedy LPT does not promise the globally optimal partition; imbalance is
    # bounded by the largest job. This sequence produces 120 versus 150.
    assert abs(loads[1]-loads[2])<=max(s.analysis.overall_difficulty for s in samples)
    assert sorted(loads.values())==[120,150]

def test_unavailable_scores_not_silently_balanced_as_zero():
    with pytest.raises(ValueError,match='unavailable difficulty'):
        balance([sample(1,None)],[NS(id=1)])

def test_empty_edge_bucket_redistributes():
    config=SamplingRequest(mode='count',budget=3,weights={'random':0,'difficulty':0,'edge':1})
    result=choose_samples([sample(i,10) for i in range(5)],config)
    assert len(result)==3 and set(result.values())=={'coverage_fallback'}

@pytest.mark.parametrize('data',[{'overall_weights':{'annotation':.2,'visual':.2}},{'bbox_weights':{'x':1}},{'tiny_threshold':0}])
def test_invalid_settings(data):
    with pytest.raises(ValueError): ScoringSettings(**data)
