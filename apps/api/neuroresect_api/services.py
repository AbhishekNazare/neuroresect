"""Application services connect persisted research inputs to neurocore."""

from typing import Any

from neurocore import demo
from neurocore.validation import validate_connectome

from .errors import APIError
from .repository import Repository, stable_hash, utcnow
from .schemas import ConnectomeImport, ScenarioCreate


class ResearchService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def patients(self) -> list[dict[str, Any]]:
        patients = {patient["id"]: patient for patient in demo.list_patients()}
        for record in self.repository.imports():
            patient = record["patient"]
            if patient["id"] in patients:
                atlases = patients[patient["id"]]["available_atlases"]
                for atlas in patient["available_atlases"]:
                    if atlas not in atlases:
                        atlases.append(atlas)
            else:
                patients[patient["id"]] = patient
        return list(patients.values())

    def patient(self, patient_id: str) -> dict[str, Any]:
        patient = next((item for item in self.patients() if item["id"] == patient_id), None)
        if patient is None:
            raise APIError(404, "PATIENT_NOT_FOUND", "Patient does not exist.")
        return patient

    def atlases(self) -> list[dict[str, Any]]:
        atlases = {atlas["id"]: atlas for atlas in demo.list_atlases()}
        for record in self.repository.imports():
            connectome = record["connectome"]
            atlas_id = connectome["atlas_id"]
            atlases.setdefault(
                atlas_id,
                {
                    "id": atlas_id,
                    "name": atlas_id,
                    "region_count": len(connectome["nodes"]),
                    "synthetic": connectome["synthetic"],
                    "description": "User imported region definitions and coordinates.",
                },
            )
        return list(atlases.values())

    def connectome(self, patient_id: str, atlas_id: str) -> dict[str, Any]:
        patient = self.patient(patient_id)
        if atlas_id not in patient["available_atlases"]:
            raise APIError(404, "CONNECTOME_NOT_FOUND", "Patient has no connectome for this atlas.")
        imported = self.repository.imported_connectome(patient_id, atlas_id)
        if imported is not None:
            return imported
        try:
            return demo.get_connectome(patient_id, atlas_id)
        except ValueError as exc:
            raise APIError(404, "CONNECTOME_NOT_FOUND", str(exc)) from exc

    def create_scenario(self, request: ScenarioCreate) -> dict[str, Any]:
        connectome = self.connectome(request.patient_id, request.atlas_id)
        self.validate_region_ids(connectome, [region.region_id for region in request.regions])
        return self.repository.create_scenario(request.model_dump())

    @staticmethod
    def validate_region_ids(connectome: dict[str, Any], region_ids: list[int]) -> None:
        unknown = sorted(set(region_ids) - {node["id"] for node in connectome["nodes"]})
        if unknown:
            raise APIError(
                422,
                "INVALID_RESECTION",
                "Region IDs are absent from this atlas.",
                {"unknown_region_ids": unknown},
            )

    def import_connectome(self, request: ConnectomeImport) -> dict[str, Any]:
        if any(patient["id"] == request.patient_id for patient in demo.list_patients()):
            raise APIError(409, "RESERVED_PATIENT_ID", "Synthetic demo patient IDs are reserved.")
        if any(atlas["id"] == request.atlas_id for atlas in demo.list_atlases()):
            raise APIError(409, "RESERVED_ATLAS_ID", "Synthetic demo atlas IDs are reserved.")
        raw = request.model_dump(exclude={"patient_label", "deidentified"})
        try:
            connectome = validate_connectome(raw)
        except ValueError as exc:
            raise APIError(422, "INVALID_CONNECTOME", str(exc)) from exc
        for existing in self.repository.imports():
            other = existing["connectome"]
            if other["atlas_id"] == request.atlas_id and other["nodes"] != connectome["nodes"]:
                raise APIError(
                    409,
                    "ATLAS_DEFINITION_CONFLICT",
                    "This atlas ID already has different region definitions or coordinates.",
                )
            if other["patient_id"] == request.patient_id and (
                other["dataset_id"] != request.dataset_id or other["synthetic"] != request.synthetic
            ):
                raise APIError(
                    409,
                    "PATIENT_METADATA_CONFLICT",
                    "Patient dataset and synthetic status must match the existing import.",
                )
        checksum = stable_hash(connectome)
        connectome["import_provenance"] = {
            "imported_at": utcnow().isoformat(),
            "sha256": checksum,
            "deidentified_acknowledged": True,
            "format": "connectome-json-v1",
        }
        patient = {
            "id": request.patient_id,
            "dataset_id": request.dataset_id,
            "label": request.patient_label or request.patient_id,
            "age": None,
            "sex": None,
            "epilepsy_duration": None,
            "modalities": ["DWI"],
            "available_atlases": [request.atlas_id],
            "synthetic": request.synthetic,
        }
        self.repository.save_import(patient, connectome)
        return {
            "patient": patient,
            "atlas_id": request.atlas_id,
            "region_count": len(connectome["nodes"]),
            "edge_count": len(connectome["edges"]),
            "provenance": connectome["import_provenance"],
        }

    def scenario_export(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.repository.scenario(scenario_id)
        connectome = self.connectome(scenario["patient_id"], scenario["atlas_id"])
        return {
            "scenario": scenario,
            "simulation": self.repository.result(scenario_id, "simulation"),
            "prediction": self.repository.result(scenario_id, "prediction"),
            "sensitivity": self.repository.result(scenario_id, "sensitivity"),
            "counterfactuals": self.repository.result(scenario_id, "counterfactuals"),
            "connectome": connectome,
            "provenance": {
                "export_format": "neuroresect-scenario-v1",
                "exported_at": utcnow().isoformat(),
                "dataset_id": connectome["dataset_id"],
                "atlas_id": scenario["atlas_id"],
                "synthetic": connectome["synthetic"],
                "connectome_sha256": stable_hash(connectome),
                "research_only": True,
            },
        }
