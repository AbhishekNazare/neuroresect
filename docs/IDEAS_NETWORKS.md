# Working with the real IDEAS II network archive

The publisher's `networks.zip` (Figshare file **68572654**) contains nested probabilistic and deterministic tractography ZIPs. This derivative snapshot is pinned by file ID and local SHA-256 separately from the OpenNeuro raw-imaging commit. Do not assume the collections have identical subject coverage or release dates.

## Acquire the pinned archive

```sh
.venv/bin/neuroresect dataset-download configs/datasets/ideas-networks-manifest.json \
  --destination data/ideas/downloads --max-bytes 3000000000
```

The original download is 2,891,080,351 bytes. Its SHA-256 is `373c810bd3b8e437c6bda92bbc993400bb7c1aa45349789419055bfdfdde9aa3`. This fingerprint was computed locally after acquisition over HTTPS; it is not an independently supplied publisher checksum. The source's multipart S3 ETag must not be represented as a whole-file MD5 checksum. Subsequent acquisitions are checked against the pinned SHA-256.

## Inspect and cache

```sh
.venv/bin/neuroresect ideas-networks data/ideas/downloads/networks.zip \
  --cache data/ideas/networks --output data/ideas/network-inventory
```

This extracts only the two expected nested archives. The outer member CRC is verified while reading, then SHA-256 fingerprints are recorded. Unchanged verified caches can be reused. Unsafe paths, duplicate members, symlinks, encrypted entries, and oversized archives are rejected. macOS metadata is ignored when indexing scientific files. Archives and derived data stay under the Git-ignored `data/` directory.

The inventories preserve subject and session identifiers, atlas variant, tractography method, weight measure, file size and source CRC. Unrecognized filenames are listed explicitly. Inventory alone does not validate every numeric matrix or every inner member CRC.

## Inspect an individual matrix

Use an exact member path from the inventory:

```sh
.venv/bin/neuroresect ideas-matrix data/ideas/networks/probabilistic_tractography.zip \
  --member probabilistic_tractography/Lausanne-125/sub-445/ses-2/dwi/sub-445_ses-2_Probabilistic-Tractography_125-Lausanne_Count.csv \
  --output data/ideas/source-matrix.json
```

The CSV's CRC and numeric graph conventions are checked. The resulting JSON is a **source matrix artifact**, not a workstation-ready connectome. It intentionally contains no invented region labels, coordinates, resection fractions or outcomes. Anatomical mapping remains explicitly unverified.

## Audit one atlas across subjects

```sh
.venv/bin/neuroresect ideas-matrix-audit data/ideas/networks/probabilistic_tractography.zip \
  --atlas Lausanne-125 --measure Count --output data/ideas/count-matrix-audit.json
```

Every matching CSV is read and CRC-checked. The audit records numeric validity, region count, positive undirected edge count, isolated regions and source hashes. Failed matrices remain in the report with a reason; an invalid matrix produces exit code 2. Empty selections fail. No matrix is symmetrized beyond the core's existing rounding tolerance, imputed, or stripped of isolated regions. The core currently accepts 2–500 nodes.

## Scientific interpretation

- Keep probabilistic and deterministic tractography separate unless an experiment explicitly compares them.
- Keep atlas scales and dilated variants separate. Atlas names are not node counts: the observed Lausanne-125 sample has 233 nodes.
- `Count` and `CountScaled` are candidates for strength-weighted analysis, subject to review of the publisher's processing definitions. `MeanFA`, `MeanMD` and `MeanLength` remain distinct measures. In particular, MD and length cannot be passed off as connection strengths.
- Patient/control status cannot be inferred from filenames. The clinical dictionary and a reviewed subject-ID join must establish cohort membership and outcome coding.
- Ordered region labels and compatible anatomical definitions are required before registration in the UI. Resection percentages must be mapped to the matching atlas; a table for another atlas is not interchangeable.
- No real outcome model has been trained by these commands. See [the integration gates](IDEAS_INTEGRATION.md).


## Observed acquisition results

| Check | Probabilistic | Deterministic |
| --- | ---: | ---: |
| Subjects | 288 | 288 |
| Matrix CSVs | 11,520 | 11,039 |
| Atlas variants | 8 | 8 |
| Missing subject/session/atlas/measure combinations within the observed archive grid | 0 | 481 |
| Lausanne-36 Count matrices passing numeric and member CRC checks | 288 | 288 |
| Regions in each audited Lausanne-36 Count matrix | 82 | 82 |

Both methods cover the same 288 subject IDs, all present in the pinned OpenNeuro diffusion inventory. The other 26 OpenNeuro diffusion subjects have no network files in this derivative archive. No cause for those omissions is inferred. A model study must select and report a common cohort for its chosen method, atlas and measure; an inventory's subject total is not the number of outcome-labelled surgical cases.

The batch audit above validates 576 Count matrices, not every CSV in the release. The outer CRC checks cover the complete bytes of both nested ZIPs; individual inner CSV CRC and numerical checks occur when selected matrices are read. `ideas-networks` lists every missing combination separately in each inventory for reproducible exclusions.
