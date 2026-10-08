# ADR 001: independent scientific core and weighted resection

Status: accepted.

The UI must not be the only place an analysis can run. `neurocore` owns validation, simulation, metrics, feature extraction, experiments, and provenance. It imports no web framework or persistence layer. The API orchestrates it; the UI displays its results; the CLI provides headless access.

Weighted resection is the default: `W′ = diag(1 − f) W diag(1 − f)`. The matrix is copied before modification. This is a graph perturbation model, not a biophysical model of neuronal recovery or seizure propagation.

Connection strength becomes shortest-path distance via `distance = 1 / positive_weight`. Disconnected node pairs contribute zero efficiency. We implement weighted efficiency explicitly because [NetworkX global_efficiency ignores weights](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.efficiency_measures.global_efficiency.html).

For both binary and weighted simulation we retain original atlas node indexing. Binary fractions at least 0.5 remove incident edges, leaving isolated nodes. This deliberately differs from literal node deletion in LLD §16: it preserves a comparable denominator and prevents apparent improvement merely from dropping disconnected nodes. The convention is recorded in provenance.

Viewer edge thresholds never enter a simulation implicitly. Scientific thresholds must be explicit and included in result hashes.
