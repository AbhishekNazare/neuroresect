import json

import numpy as np
import pytest
from neurocore.cli import main
from neurocore.io import export_connectome, import_connectome, read_json, write_json


def test_json_and_csv_round_trip(tmp_path, line_connectome):
    path = tmp_path / "connectome.json"
    export_connectome(line_connectome, path)
    imported = import_connectome(path)
    assert imported["matrix"] == line_connectome["matrix"]
    csv_path = tmp_path / "matrix.csv"
    np.savetxt(csv_path, line_connectome["matrix"], delimiter=",")
    metadata = {key: value for key, value in line_connectome.items() if key != "matrix"}
    metadata_path = write_json(tmp_path / "metadata.json", metadata)
    assert import_connectome(csv_path, metadata_path) == imported
    with pytest.raises(ValueError):
        import_connectome(csv_path)


def test_cli_simulation_and_error(tmp_path, line_connectome, capsys):
    input_path = export_connectome(line_connectome, tmp_path / "input.json")
    regions_path = write_json(tmp_path / "regions.json", [{"region_id": 1, "fraction_removed": 0.5}])
    output_path = tmp_path / "simulation.json"
    assert main(["simulate", "--input", str(input_path), "--regions", str(regions_path), "--output", str(output_path)]) == 0
    assert read_json(output_path)["connectivity_loss"] > 0
    assert main(["inspect", "unknown"]) == 2
    assert "Unknown patient" in capsys.readouterr().err


def test_strict_nonfinite_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"weight": NaN}')
    with pytest.raises(ValueError):
        read_json(path)
    with pytest.raises(ValueError):
        write_json(path, {"weight": float("nan")})


def test_cli_lists(capsys):
    assert main(["atlases"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
