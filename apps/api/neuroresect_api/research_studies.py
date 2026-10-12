"""Packaged, aggregate-only research reports; never deserialize model binaries."""

import json
from importlib.resources import files

from .errors import APIError

STUDY_ID = "ideas-year1-baseline-v1"


def study_report(study_id: str) -> dict:
    if study_id != STUDY_ID:
        raise APIError(404, "NOT_FOUND", "Research study not found")
    return json.loads(files("neuroresect_api").joinpath(f"reports/{STUDY_ID}.json").read_text())
