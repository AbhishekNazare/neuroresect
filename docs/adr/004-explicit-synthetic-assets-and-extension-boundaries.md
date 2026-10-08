# ADR 004: explicit synthetic assets and supported extensions

Status: accepted.

No approved dataset or licensed anatomical meshes were present in the repository. Ship a deterministic synthetic cohort and two synthetic atlas resolutions, `demo-64` and `demo-96`. Their geometry illustrates a brain-shaped network; it must not be described as a named anatomical atlas or patient-specific surface.

Support validated de-identified connectome imports with explicit region metadata. Real tract intersections and voxel-mask expansion require imaging/tractography inputs; resection fraction changes must never be labeled as millimeters. Counterfactuals are constrained graph scenarios, not recommended operations.

DWI-derived connectivity is the implemented modality. MEG, fMRI, HGM, and EEG integration remain explicit extension work, consistent with HLD phase 8 and LLD §§122–124. Model compatibility is visible; the system must not silently select a different model or run a synthetic-trained outcome model on real imported data.
