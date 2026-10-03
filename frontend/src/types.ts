export type Feature = {
  value: number | null;
  raw: unknown;
  available: boolean;
  reason_if_unavailable: string | null;
};
export type Analysis = {
  visual: {
    features: Record<string, Feature>;
    score: number | null;
    contributions: Record<string, number>;
  };
  per_type: Record<
    string,
    {
      features: Record<string, Feature>;
      score: number | null;
      contributions: Record<string, number>;
    }
  >;
  feature_contributions: Record<string, number>;
  rare_classes: string[];
};
export type Annotation = {
  id: number;
  label: string;
  shape_type: string;
  geometry: Record<string, any>;
  attributes: Record<string, unknown>;
  occluded: boolean | null;
  metadata: Record<string, unknown>;
};
export type Sample = {
  id: number;
  file_name: string;
  task_type: string;
  width: number | null;
  height: number | null;
  annotation_count: number;
  media_url: string | null;
  media_kind: string | null;
  annotation_difficulty: number | null;
  visual_difficulty: number | null;
  overall_difficulty: number | null;
  level: string;
  rare_classes: string[];
  analysis?: Analysis;
  annotations?: Annotation[];
  sampling_reason?: string;
  assignment_id?: number;
  reviewer_id?: number;
  reviewer?: string;
  status?: string;
  note?: string;
  needs_regeneration?: boolean;
};
export type Dataset = {
  id: number;
  name: string;
  format: string;
  task_type: string;
  revision: number;
  sample_count: number;
  annotation_count: number;
  average_difficulty: number | null;
  levels: Record<string, number>;
  classes: Record<string, number>;
  annotation_types: Record<string, number>;
  rare_classes: string[];
  missing_media: number;
  warnings: string[];
};
export type Run = {
  id: number;
  config: unknown;
  needs_regeneration: boolean;
  selections: Sample[];
};
export type Reviewer = { id: number; name: string };
export type Settings = Record<string, Record<string, number> | number>;
