"""Bounded, strict public request schemas; no filesystem paths are accepted."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
RegionID = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class Region(RequestModel):
    region_id: RegionID
    fraction_removed: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ScenarioCreate(RequestModel):
    patient_id: Identifier
    atlas_id: Identifier = "demo-64"
    label: str = Field(default="Research scenario", min_length=1, max_length=120)
    method: Literal["weighted", "binary"] = "weighted"
    regions: list[Region] = Field(default_factory=list, max_length=500)

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, regions: list[Region]) -> list[Region]:
        if len({region.region_id for region in regions}) != len(regions):
            raise ValueError("Region IDs must be unique")
        return regions


class Constraints(RequestModel):
    minimum_target_coverage: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    protected_regions: list[RegionID] = Field(default_factory=list, max_length=500)
    max_candidates: int = Field(default=5, ge=1, le=50)

    @field_validator("protected_regions")
    @classmethod
    def unique_regions(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("Protected region IDs must be unique")
        return values


class ExperimentCreate(RequestModel):
    name: str = Field(default="Synthetic A/B/C comparison", min_length=1, max_length=120)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    folds: int = Field(default=5, ge=2, le=10)
    n_patients: int = Field(default=80, ge=24, le=240)
    model_type: Literal["logistic", "random_forest", "svm"] = "logistic"
    atlas_id: Identifier = "demo-64"


class Node(RequestModel):
    id: RegionID
    name: str = Field(min_length=1, max_length=120)
    hemisphere: Literal["L", "R", "M"]
    network: str = Field(min_length=1, max_length=80)
    x: FiniteFloat
    y: FiniteFloat
    z: FiniteFloat


class ConnectomeImport(RequestModel):
    deidentified: Literal[True]
    patient_id: Identifier
    atlas_id: Identifier
    dataset_id: Identifier
    patient_label: str | None = Field(default=None, min_length=1, max_length=120)
    synthetic: bool = False
    nodes: list[Node] = Field(min_length=2, max_length=500)
    matrix: list[list[FiniteFloat]] = Field(min_length=2, max_length=500)
    actual_resection: list[Region] = Field(default_factory=list, max_length=500)

    @field_validator("matrix")
    @classmethod
    def bounded_rows(cls, matrix: list[list[float]]) -> list[list[float]]:
        if any(len(row) != len(matrix) for row in matrix):
            raise ValueError("Matrix must be square")
        return matrix
