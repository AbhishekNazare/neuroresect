export type Patient = {
  id: string;
  dataset_id: string;
  label: string;
  age: number | null;
  sex: string | null;
  epilepsy_duration: number | null;
  modalities: string[];
  available_atlases: string[];
  synthetic: boolean;
};
export type Atlas = {
  id: string;
  name: string;
  region_count: number;
  synthetic: boolean;
  description: string;
};
export type Region = {
  id: number;
  name: string;
  hemisphere: string;
  network: string;
  x: number;
  y: number;
  z: number;
  strength?: number;
  is_hub?: boolean;
};
export type Edge = { source: number; target: number; weight: number };
export type Resection = { region_id: number; fraction_removed: number };
export type Connectome = {
  patient_id: string;
  atlas_id: string;
  dataset_id: string;
  synthetic: boolean;
  nodes: Region[];
  edges: Edge[];
  matrix?: number[][];
  actual_resection: Resection[];
};
export type Scenario = {
  id: string;
  patient_id: string;
  atlas_id: string;
  label: string;
  method: "weighted" | "binary";
  regions: Resection[];
  created_at: string;
};
export type Metrics = {
  efficiency: number;
  density: number;
  clustering: number;
  modularity: number;
  components: number;
  largest_component_fraction: number;
  path_length: number;
};
export type Provenance = Record<string, unknown>;
export type Simulation = {
  baseline: Metrics;
  post: Metrics;
  delta: Metrics;
  relative_delta: Metrics;
  connectivity_loss: number;
  impacted_hubs: unknown[];
  hub_damage: number;
  removed_edges: number;
  nodes: Region[];
  edges: Edge[];
  provenance: Provenance;
};
export type Prediction = {
  probability: number;
  interval: { lower: number; upper: number; level: number; method: string };
  model: { id: string; name: string; version: string };
  feature_version: string;
  synthetic: boolean;
  contributions: { feature: string; value: number }[];
  provenance: Provenance;
};
export type Sensitivity = {
  variants: {
    label: string;
    offset: number;
    regions: Resection[];
    connectivity_loss: number;
    efficiency: number;
    efficiency_delta: number;
  }[];
  region_scores: { region_id: number; score: number }[];
  provenance: Provenance;
};
export type Candidate = {
  id: string;
  label: string;
  regions: Resection[];
  target_coverage: number;
  connectivity_loss: number;
  hub_damage: number;
  objective_score: number;
  efficiency: number;
};
export type Counterfactual = {
  candidates: Candidate[];
  constraints: Record<string, unknown>;
  provenance: Provenance;
};
export type ExperimentModel = {
  roc_curve?: { fpr: number[]; tpr: number[] };
  precision_recall_curve?: { precision: number[]; recall: number[] };
  calibration?: { predicted: number[]; observed: number[] };
  name: string;
  feature_set: string[] | string;
  metrics: Record<string, number | null>;
  fold_metrics: Record<string, unknown>[];
  predictions: unknown[];
};
export type Experiment = {
  id: string;
  name: string;
  status: string;
  dataset_id: string;
  atlas_id: string;
  seed: number;
  models: Record<string, ExperimentModel>;
  folds: unknown;
  provenance: Provenance;
};
export type Job<T> = {
  id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  progress: number;
  stage: string;
  result: T | null;
  error: { message?: string } | string | null;
};
export type Tab = "workspace" | "scenarios" | "experiments" | "pipeline";
