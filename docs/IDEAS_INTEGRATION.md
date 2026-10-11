# IDEAS / IDEAS II integration

## Current status

The acquisition and audit tools are implemented. **Real outcome training is not yet implemented or performed.** This phase does not make the bundled synthetic model compatible with real patients.

The pinned OpenNeuro `ds007401` version `1.0.0` inventory contains 542 subject directories: 541 with T1w imaging, 492 with FLAIR, and 314 with diffusion imaging. These are modality-availability counts, not surgical training-cohort counts. Patient/control membership is not inferred from identifiers.

The initial acquisition verified eight metadata files (10,940 bytes). The subsequent acquisition downloaded the real `networks.zip` archive (2,891,080,351 bytes), verified both nested archives by CRC, and indexed 288 subjects. Both Lausanne-36 Count audits passed: 288 matrices per tractography method, each with 82 regions. Clinical outcomes and resection tables are now acquired and joined; no real outcome model has been trained yet. Local files and reports are under `data/ideas/`, excluded from Git. See [network acquisition and audit commands](IDEAS_NETWORKS.md).

The publisher's [catalogue](https://www.cnnp-lab.com/ideas-data) and [OpenNeuro README](https://github.com/OpenNeuroDatasets/ds007401/blob/2e7f2573a5f8a9921cb19fca5e601bc141633f49/README.md) distinguish raw imaging on OpenNeuro from processed derivatives and clinical tables on Figshare. The user supplied direct file links for all five clinical/label/resection companions; those files are now acquired. The verified join yields 182 eligible year-one surgical cases. See [cohort mapping and exclusions](IDEAS_COHORT.md).

## Reproducible acquisition

```sh
.venv/bin/neuroresect ideas-discover --output data/ideas/source --subject sub-1
.venv/bin/neuroresect dataset-download data/ideas/source/manifest.json \
  --destination data/ideas/raw --max-bytes 1000000
```

Discovery pins Git commit `2e7f2573a5f8a9921cb19fca5e601bc141633f49`, rejects truncated inventories, and writes the original tree, subject inventory, and metadata manifest. Repeat `--subject` to select additional subjects. The default is `sub-1`. Git-annex symlink pointers are **not** downloaded as if they were MRI volumes.

Downloads verify the publisher's checksum before promoting `.part` files. Existing valid files are reused. Interrupted downloads resume using HTTP Range; a server that ignores Range causes a clean restart. Invalid ranges, checksum mismatches, excessive bytes, unsafe paths, and symlink escapes fail explicitly. A corrupt completed `.part` must be removed before retrying. Acquisition reports record SHA-256 for every completed file and the manifest itself. No archives are automatically extracted. Downloads are sequential; concurrent writers to the same destination are unsupported.

For Figshare, create a versioned manifest from the resolved file metadata:

```json
{
  "schema_version": 1,
  "dataset_id": "ideas-ii-pinned-release",
  "scope": "processed-connectomes",
  "assets": [{
    "path": "connectomes.zip",
    "url": "https://publisher.example/actual-file-download",
    "size": 12345,
    "algorithm": "md5",
    "digest": "00000000000000000000000000000000"
  }]
}
```

This example is a **schema illustration, not a usable source**. Supply the actual byte size and checksum from the publisher. Supported algorithms are SHA-256, Figshare-style MD5 (transfer integrity), and Git blob SHA-1. Preserve the source URL, version, licence and metadata alongside the manifest. [Source catalogue](../configs/datasets/ideas-sources.json) lists the required collections; it is not itself a download manifest.

## Cohort audit contract

After examining the actual clinical dictionary and atlas definitions, a reviewed mapping must create a normalized cohort JSON. Do not guess column names, outcome coding, atlas order, or ID transformations.

```json
{
  "schema_version": 1,
  "dataset_id": "ideas-ii-pinned-release",
  "endpoint": {
    "definition": "Specify the exact clinical scale, positive class, and follow-up rule",
    "followup_months": 12
  },
  "subjects": [{
    "subject_id": "sub-1",
    "group": "unknown",
    "outcome": null,
    "followup_months": null,
    "connectome": null,
    "atlas_alignment_reviewed": false,
    "source_refs": []
  }]
}
```

```sh
.venv/bin/neuroresect cohort-audit data/ideas/cohort.json \
  --output data/ideas/cohort-audit.json
```

`connectome` is a relative path to a validated [connectome JSON](DATA_IMPORT.md), with explicit patient ID, dataset ID, atlas nodes and real resection fractions. Each subject has a single row; duplicate IDs fail rather than multiplying observations. Groups are `surgical_patient`, `healthy_control`, or `unknown`. Binary outcome values must come from an explicit source mapping; null stays missing. Follow-up must exactly match the declared endpoint. Controls cannot enter the surgical outcome cohort.

The report includes all exclusion reasons, eligible class counts, and input hashes. Eligibility requires a non-synthetic valid connectome, matching identities, positive actual resection fractions, an explicit atlas-alignment review, source references, and known outcome at the specified follow-up. These checks establish structural eligibility for retrospective analysis; they do not independently prove anatomical registration, source interpretation, or model suitability. Clinical-covariate and model-specific validation remain separate.

## Next acceptance gates

1. Networks and all five companion files are acquired and fingerprinted.
2. Network, clinical, label and resection adapters are implemented; the 182-case cohort and exclusions are recorded.
3. Lausanne-36 region-name mapping is verified; confirm the explicit fractional-unit interpretation against source imaging/methods and obtain anatomical coordinates/surfaces.
4. Export one real patient through the existing import/simulation pipeline; only then scale to all eligible subjects.
5. Freeze the outcome definition and cohort audit before implementing real-data A/B/C evaluation.

Raw preprocessing, anatomy integration, real model evaluation/registry, anatomical editing, lab deployment and multimodal work remain tracked in [the delivery plan](DELIVERY_PLAN.md). Postoperative resection information supports retrospective experiments; prospective performance requires separate evaluation.
