from abc import ABC, abstractmethod
from collections import Counter
from itertools import combinations
import math
import cv2
import numpy as np

def feature(value=None, raw=None, reason=None):
    return {'value': None if value is None else round(min(1,max(0,float(value))),6), 'raw':raw, 'available':value is not None, 'reason_if_unavailable':reason if value is None else None}

def combine(features, weights):
    available = {k:w for k,w in weights.items() if features.get(k,{}).get('available') and w > 0}
    total = sum(available.values())
    if not total:
        return None, {}
    contributions = {k:100*features[k]['value']*w/total for k,w in available.items()}
    return round(sum(contributions.values()),4), {k:round(v,4) for k,v in contributions.items()}

def area(box):
    return max(0,box['x2']-box['x1'])*max(0,box['y2']-box['y1'])

def iou(a,b):
    intersection = max(0,min(a['x2'],b['x2'])-max(a['x1'],b['x1']))*max(0,min(a['y2'],b['y2'])-max(a['y1'],b['y1']))
    union = area(a)+area(b)-intersection
    return intersection/union if union > 0 else 0

def polygon_area(points):
    return abs(sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(points, points[1:]+points[:1])))/2

def envelope(points):
    xs,ys = zip(*points)
    return dict(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))

def pair_ratio(items, predicate):
    if len(items)>2000:
        return feature(reason='Pairwise metrics unavailable above 2,000 instances to bound local CPU cost')
    pair_count = len(items)*(len(items)-1)//2
    count = sum(bool(predicate(a,b)) for a,b in combinations(items,2))
    return feature(count/pair_count if pair_count else 0, {'pairs':count,'possible_pairs':pair_count})

def image_analysis(path, settings):
    keys = settings.visual_weights
    if not path or str(path).lower().endswith(('.bin','.pcd')):
        f = {k:feature(reason='Image media was not provided') for k in keys}
        return {'features':f,'score':None,'contributions':{}}
    image = cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
    if image is None:
        f = {k:feature(reason='Image could not be decoded') for k in keys}
        return {'features':f,'score':None,'contributions':{}}
    # Bound compute cost while retaining original dimensions for geometry analysis.
    if max(image.shape) > 1600:
        image = cv2.resize(image, None, fx=1600/max(image.shape), fy=1600/max(image.shape), interpolation=cv2.INTER_AREA)
    lap = float(cv2.Laplacian(image,cv2.CV_64F).var())
    brightness, contrast = float(image.mean()), float(image.std())
    edge = float(np.count_nonzero(cv2.Canny(image,100,200))/image.size)
    hist = np.bincount(image.ravel(),minlength=256).astype(float)/image.size
    entropy = float(-sum(hist[hist>0]*np.log2(hist[hist>0])))
    f = {'blur':feature(1/(1+lap/100),lap), 'exposure':feature(abs(brightness-127.5)/127.5,brightness), 'low_contrast':feature(1-min(contrast/64,1),contrast), 'edge_complexity':feature(edge/.2,edge), 'entropy':feature(entropy/8,entropy)}
    score, contrib = combine(f,keys)
    return {'features':f,'score':score,'contributions':contrib}

class BaseDifficultyAnalyzer(ABC):
    weights_key = ''
    @abstractmethod
    def features(self, annotations, width, height, rare_labels, settings):
        pass

    def analyze(self, annotations, width, height, rare_labels, settings):
        f = self.features(annotations,width,height,rare_labels,settings)
        score,contrib = combine(f,getattr(settings,self.weights_key))
        return {'features':f,'score':score,'contributions':contrib,'annotation_count':len(annotations)}

def common(annotations, rare_labels):
    n = len(annotations)
    return {'count':feature(n/20,n), 'rare':feature(sum(a.label in rare_labels for a in annotations)/n if n else 0, sorted({a.label for a in annotations if a.label in rare_labels}))}

class BBoxDifficultyAnalyzer(BaseDifficultyAnalyzer):
    weights_key = 'bbox_weights'
    def features(self,a,w,h,rare,s):
        f = common(a,rare)
        image_area = w*h if w and h else None
        tiny = sum(area(x.geometry)/image_area < s.tiny_threshold for x in a) if image_area else None
        known = [x for x in a if x.occluded is not None]
        f.update(tiny=feature(tiny/len(a) if tiny is not None and a else None, tiny, 'Image dimensions unavailable'), occlusion=feature(sum(x.occluded for x in known)/len(known) if known else None,{'known_objects':len(known),'occluded_objects':sum(bool(x.occluded) for x in known)},'Source does not encode occlusion'), overlap=pair_ratio(a,lambda x,y:iou(x.geometry,y.geometry)>s.overlap_threshold))
        return f

class SegmentationDifficultyAnalyzer(BaseDifficultyAnalyzer):
    weights_key = 'segmentation_weights'
    def features(self,a,w,h,rare,s):
        f = common(a,rare)
        polygons = [x.geometry['points'] for x in a if x.shape_type == 'POLYGON']
        complete = len(polygons) == len(a)
        image_area = w*h if w and h else None
        f['tiny'] = feature(sum(polygon_area(p)/image_area<s.tiny_threshold for p in polygons)/len(polygons) if complete and image_area and polygons else None, reason='Requires polygon geometry and image dimensions')
        f['complexity'] = feature(sum(min(len(p)/50,1) for p in polygons)/len(polygons) if complete and polygons else None, {'vertices':sum(len(p) for p in polygons),'region_area':sum(polygon_area(p) for p in polygons)}, 'RLE mask boundary metrics are unavailable')
        # Bounding envelopes are explicitly a crowding proxy, not polygon IoU.
        f['crowding'] = pair_ratio([envelope(p) for p in polygons],lambda x,y:iou(x,y)>s.overlap_threshold) if complete else feature(reason='RLE crowding metrics unavailable')
        known = [x for x in a if x.occluded is not None]
        f['occlusion_metadata'] = feature(sum(x.occluded for x in known)/len(known) if known else None,reason='Source does not encode occlusion; informational metric')
        return f

class KeypointDifficultyAnalyzer(BaseDifficultyAnalyzer):
    weights_key = 'keypoint_weights'
    def features(self,a,w,h,rare,s):
        f = common(a,rare)
        points = [p for x in a for p in x.geometry['points']]
        known = [p for p in points if 'visibility' in p]
        f['missing'] = feature(sum(p['visibility']==0 for p in known)/len(known) if known else None, {'total_keypoints':len(points),'known_visibility':len(known),'missing_keypoints':sum(p['visibility']==0 for p in known)}, 'Source does not encode keypoint visibility')
        f['occlusion'] = feature(sum(p['visibility']==1 for p in known)/len(known) if known else None, {'occluded_keypoints':sum(p['visibility']==1 for p in known),'visible_keypoints':sum(p['visibility']==2 for p in known)}, 'Source does not encode keypoint visibility')
        envelopes = [envelope([[p['x'],p['y']] for p in x.geometry['points'] if p.get('visibility',2)>0]) for x in a if any(p.get('visibility',2)>0 for p in x.geometry['points'])]
        f['crowding'] = pair_ratio(envelopes,lambda x,y:iou(x,y)>s.overlap_threshold)
        return f

class Cuboid3DDifficultyAnalyzer(BaseDifficultyAnalyzer):
    weights_key = 'cuboid_weights'
    def features(self,a,w,h,rare,s):
        f = common(a,rare)
        known = [x for x in a if x.occluded is not None]
        trunc = [x.source_metadata['truncation'] for x in a if 'truncation' in x.source_metadata]
        f['occlusion'] = feature(sum(x.occluded for x in known)/len(known) if known else None, reason='Occlusion metadata unavailable')
        f['truncation'] = feature(sum(trunc)/len(trunc) if trunc else None, reason='Truncation metadata unavailable')
        f['proximity'] = pair_ratio(a,lambda x,y:sum((x.geometry['position'][k]-y.geometry['position'][k])**2 for k in ('x','y','z')) < 25)
        f['sparsity'] = feature(reason='Point-cloud to camera calibration and point-in-cuboid analysis are not implemented')
        f['point_density'] = feature(reason='Point-cloud to camera calibration and point-in-cuboid analysis are not implemented')
        f['distance_to_sensor'] = feature(reason='Sensor transform/calibration was not provided')
        f['projection_quality'] = feature(reason='Camera calibration was not provided')
        return f

ANALYZERS = {'BBOX_2D':BBoxDifficultyAnalyzer(), 'POLYGON':SegmentationDifficultyAnalyzer(), 'MASK':SegmentationDifficultyAnalyzer(), 'KEYPOINT':KeypointDifficultyAnalyzer(), 'CUBOID_3D':Cuboid3DDifficultyAnalyzer()}

def analyze_sample(sample, rare_labels, settings):
    visual = image_analysis(sample.media_path,settings)
    groups = {}
    for a in sample.annotations:
        kind = 'SEGMENTATION' if a.shape_type in ('POLYGON','MASK') else a.shape_type
        groups.setdefault(kind,[]).append(a)
    per_type = {k:ANALYZERS[a[0].shape_type].analyze(a,sample.width,sample.height,rare_labels,settings) for k,a in groups.items()}
    # Count-weighted mean over available type scores; no duplicate shapes across groups.
    type_weights = {k:v['annotation_count'] for k,v in per_type.items()}
    annotation, type_contrib = combine({k:feature(v['score']/100 if v['score'] is not None else None) for k,v in per_type.items()}, type_weights)
    if not sample.annotations:
        annotation = 0.0  # measured empty sample, not unavailable annotation data
    overall, overall_contrib = combine({'annotation':feature(annotation/100 if annotation is not None else None),'visual':feature(visual['score']/100 if visual['score'] is not None else None)},settings.overall_weights)
    contributions = {}
    for k,v in per_type.items():
        factor = (type_weights[k]/sum(type_weights.values())) if type_weights else 0
        factor *= overall_contrib.get('annotation',0)/annotation if annotation else 0
        for name,value in v['contributions'].items():
            contributions[k+'.'+name] = round(value*factor,4)
    visual_factor = overall_contrib.get('visual',0)/visual['score'] if visual['score'] else 0
    contributions.update({'visual.'+k:round(v*visual_factor,4) for k,v in visual['contributions'].items()})
    return dict(annotation_difficulty=annotation,visual_difficulty=visual['score'],overall_difficulty=overall,level='UNAVAILABLE' if overall is None else ('EASY' if overall<40 else 'MEDIUM' if overall<70 else 'HARD'), details={'visual':visual,'per_type':per_type,'overall_contributions':overall_contrib,'feature_contributions':contributions,'rare_classes':sorted({a.label for a in sample.annotations if a.label in rare_labels}),'settings':settings.model_dump()})
