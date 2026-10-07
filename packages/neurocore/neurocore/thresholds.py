"""Scientific graph thresholds, independent of the workstation's display filter."""

from __future__ import annotations

import numpy as np

from neurocore.validation import finite_number, validate_matrix


def threshold_matrix(matrix, strategy: str = "none", value: float = 0.0) -> np.ndarray:
    result = validate_matrix(matrix).copy()
    value = finite_number(value, "threshold")
    if strategy == "none":
        return result
    if strategy == "absolute":
        if value < 0:
            raise ValueError("Absolute threshold must be nonnegative")
        result[result <= value] = 0
    elif strategy == "percentile":
        if not 0 <= value <= 100:
            raise ValueError("Percentile must be between 0 and 100")
        positive = result[np.triu_indices(len(result), 1)]
        positive = positive[positive > 0]
        if len(positive):
            result[result < np.percentile(positive, value)] = 0
    elif strategy in ("density", "top_k"):
        mask = np.zeros(result.shape, dtype=bool)
        if strategy == "density":
            if not 0 <= value <= 1:
                raise ValueError("Density must be between 0 and 1")
            candidates = [(i, j) for i in range(len(result)) for j in range(i + 1, len(result)) if result[i, j] > 0]
            candidates.sort(key=lambda edge: (-result[edge], edge))
            count = int(np.floor(value * len(result) * (len(result) - 1) / 2))
            for i, j in candidates[:count]:
                mask[i, j] = mask[j, i] = True
        else:
            if value != int(value) or not 0 <= value < len(result):
                raise ValueError("top_k must be an integer between 0 and N-1")
            for i in range(len(result)):
                order = sorted(range(len(result)), key=lambda j: (-result[i, j], j))
                for j in order[:int(value)]:
                    if result[i, j] > 0:
                        mask[i, j] = mask[j, i] = True
        result[~mask] = 0
    else:
        raise ValueError(f"Unknown threshold strategy: {strategy}")
    return result
