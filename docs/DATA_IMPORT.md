# Importing a research connectome

The repository includes [a four-region synthetic example](../examples/connectome.json) with deliberately nonsequential region IDs. This tests that array position and region identity are kept distinct.

## JSON via API

Start the API, then:

```sh
curl --fail-with-body http://localhost:8000/api/v1/datasets/import \
  -H 'Content-Type: application/json' \
  --data-binary @examples/connectome.json
```

Reload the workstation and select `EXAMPLE-001`. Imported data supports graph exploration, virtual resection, sensitivity, constrained weighted counterfactuals, and export. The synthetic-trained outcome model rejects imported connectomes, including synthetic imports, because training-domain compatibility cannot be assumed.

The API accepts `patient_id`, `dataset_id`, `atlas_id`, `nodes`, `matrix`, `actual_resection`, `synthetic`, optional `patient_label`, and an explicit `deidentified: true` acknowledgment. This acknowledgment records the uploader's declaration; it is not an automated de-identification service.

Every node needs a unique integer `id`, a `name`, `hemisphere` (`L`, `R`, or `M`), `network`, and finite `x/y/z` coordinates. Matrix row order **must match node array order**. IDs do not need to be contiguous. Up to 500 nodes and an 8 MiB request are supported by the default limits.

The matrix must be square, symmetric within the documented floating tolerance, nonnegative, finite, and zero-diagonal. Removal fractions must be finite values in `[0,1]` with unique known region IDs. Import never guesses an atlas, silently reshapes a matrix, or repairs incompatible source data.

Duplicate patient/atlas imports return a conflict. Reusing an atlas ID with a different definition also returns a conflict. Demo patient and atlas IDs are reserved. Use versioned IDs for changed source datasets or atlas definitions.

## Headless import and simulation

```sh
.venv/bin/neuroresect import examples/connectome.json --output artifacts/imported.json
.venv/bin/neuroresect simulate --input artifacts/imported.json \
  --regions examples/resection.json --output artifacts/simulation.json
```

For CSV, supply an ordinary numeric square matrix and a JSON metadata sidecar containing the same metadata fields as the JSON example, excluding `matrix`:

```sh
.venv/bin/neuroresect import matrix.csv --metadata metadata.json \
  --output artifacts/imported.json
```

This release consumes precomputed structural connectomes. It does not run diffusion preprocessing, tractography, voxel-mask registration, or cortical segmentation. Prepare those inputs with your validated imaging pipeline and record their versions in your study provenance.
