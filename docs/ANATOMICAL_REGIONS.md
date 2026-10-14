# Atlas labels and regional resection audit

The anatomy audit establishes coordinate compatibility. This next step joins the 82 ordered IDEAS Lausanne-36 names to explicit FreeSurfer voxel IDs and computes regional geometry and mask overlap. It does not infer IDs from row numbers or replace published cohort fractions.

## Name mapping

Use the [official FreeSurfer 7.3.2 lookup table](https://raw.githubusercontent.com/freesurfer/freesurfer/v7.3.2/distribution/FreeSurferColorLUT.txt), matching the version recorded in the acquired reconstruction's statistics. The acquired table has SHA-256 `6bd6e8885ed0a085ae8e1f18b4788780b6c40a94d8afcda05f7dde1fe0bc001f`.

Cortical names use the existing explicit `ctx-lh-X` → `l.X` and `ctx-rh-X` → `r.X` normalization. Two historical naming aliases map `Left-Thalamus`/`Right-Thalamus` to the workbook's corresponding `*-Thalamus-Proper` names. Unknown names, duplicate IDs, duplicate names and missing regions fail. Every mapped region must contain voxels before its centroid or fraction can be reported.

The CLI accepts a supplied LUT and records its checksum. Its verification flag refers to correspondence with that supplied LUT; operators must verify the official source hash above. It is not an authenticity certificate for an arbitrary input table or a spatial registration certificate.

## Reproduce

Use the anatomy extra and first-case files described in [ANATOMY_AUDIT.md](ANATOMY_AUDIT.md). Also extract the regular archive member `14/mri/aparc+aseg.mgz` to the case's `mri/` directory. Keep the official LUT in `data/ideas/anatomy/FreeSurferColorLUT-v7.3.2.txt`.

```sh
.venv/bin/python -m neurocore.anatomy_regions data/ideas/anatomy/sub-14 \
  --cohort data/ideas/cohort-year1.json \
  --lut data/ideas/anatomy/FreeSurferColorLUT-v7.3.2.txt \
  --subject-id sub-14 --output data/ideas/anatomy/sub-14-regions.json
```

The output must be new. It records source hashes, the ordered mapping, region voxel counts, volumes, scanner-RAS centroids and resection fractions. Patient-level output remains under ignored `data/`; it is not bundled into the public application.

## Why there are four comparisons

The reconstruction contains both `myaparc_36.mgz` and `aparc+aseg.mgz`. The mask lives on the native MRI grid. The report evaluates both parcellations on both grids, using nearest-neighbour resampling: either move the mask onto the conformed grid or move the parcellation onto the native grid. These are explicitly separate measurements, not interchangeable estimates.

For subject 14, absolute differences from the published fractions are:

| Parcellation and comparison grid | Mean absolute difference | Maximum absolute difference |
| --- | ---: | ---: |
| myaparc_36, conformed | 0.003008 | 0.115039 |
| myaparc_36, native | 0.002808 | 0.116631 |
| aparc+aseg, conformed | 0.000860 | 0.019953 |
| aparc+aseg, native | 0.000682 | 0.020144 |

Differences are in fraction units: 0.02 means two percentage points. The alternative parcellation explains much of this case's discrepancy, but none of the four methods reproduces the published table exactly. Resampling direction alone does not explain the larger differences. Source preprocessing, mask version and region-definition details still need reconciliation. These observations support further investigation; they do not establish the publisher's exact method or cohort-wide units.

The baseline training inputs remain unchanged. The report never selects the closest method automatically or marks the published fractions as reproduced. A reviewed patient view may show computed regions with their method and limitations, but cannot claim clinical validation from this audit.
