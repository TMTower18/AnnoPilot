from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
import math

class ScoringSettings(BaseModel):
    overall_weights: Dict[str, float] = {'annotation': .7, 'visual': .3}
    visual_weights: Dict[str, float] = {'blur': .3, 'exposure': .25, 'low_contrast': .2, 'edge_complexity': .15, 'entropy': .1}
    bbox_weights: Dict[str, float] = {'count': .2, 'tiny': .25, 'occlusion': .2, 'overlap': .2, 'rare': .15}
    segmentation_weights: Dict[str, float] = {'count': .2, 'tiny': .2, 'complexity': .25, 'crowding': .2, 'rare': .15}
    keypoint_weights: Dict[str, float] = {'count': .2, 'missing': .25, 'occlusion': .25, 'crowding': .15, 'rare': .15}
    cuboid_weights: Dict[str, float] = {'count': .2, 'occlusion': .2, 'truncation': .2, 'proximity': .15, 'rare': .15, 'sparsity': .1}
    tiny_threshold: float = Field(.01, gt=0, le=1)
    overlap_threshold: float = Field(.3, ge=0, le=1)
    rare_threshold: float = Field(.05, gt=0, le=1)

    @model_validator(mode='after')
    def validate_weights(self):
        for name in ('overall', 'visual', 'bbox', 'segmentation', 'keypoint', 'cuboid'):
            weights = getattr(self, name + '_weights')
            expected = set(type(self).model_fields[name + '_weights'].default)
            if set(weights) != expected or any(not math.isfinite(v) or v < 0 or v > 1 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-6:
                raise ValueError(name + ' weights must contain the expected keys and sum to 1')
        return self

class SamplingRequest(BaseModel):
    mode: Literal['percentage', 'count'] = 'percentage'
    budget: float = Field(10, gt=0)
    seed: int = 42
    weights: Dict[str, float] = {'random': .4, 'difficulty': .4, 'edge': .2}

    @model_validator(mode='after')
    def check(self):
        if not math.isfinite(self.budget):
            raise ValueError('Budget must be finite')
        if set(self.weights) != {'random', 'difficulty', 'edge'} or any(not math.isfinite(v) or v < 0 or v > 1 for v in self.weights.values()) or abs(sum(self.weights.values()) - 1) > 1e-6:
            raise ValueError('Sampling weights must sum to 1')
        if self.mode == 'percentage' and self.budget > 100:
            raise ValueError('Percentage must be at most 100')
        if self.mode == 'count' and self.budget != int(self.budget):
            raise ValueError('Sample count must be a whole number')
        return self

class ReviewerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class ReviewRequest(BaseModel):
    status: Literal['REVIEWED', 'ISSUE_FOUND', 'SKIPPED', 'PENDING']
    note: str = Field('', max_length=10000)
