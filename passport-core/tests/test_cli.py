from __future__ import annotations

import json
from pathlib import Path

from passport_core.cli import _collect_image_sources, main
from passport_core.models import BoundingBox, FaceCropResult, PassportData, PassportProcessingResult


def test_cli_process_outputs_unified_results(monkeypatch, capsys, tmp_path: Path):
    result = PassportProcessingResult(
        source="a.jpg",
        trace_id="trace-1",
        passport_image_uri="orig://1",
        face_crop_uri="faces://1",
        data=PassportData(PassportNumber="A123"),
    )

    class StubService:
        def __init__(self, settings=None) -> None:
            self.settings = settings

        def process_sources(self, sources):
            assert sources == ["a.jpg", "b.jpg"]
            return [result]

        def export_results_csv(self, results, output_path):
            output_path.write_text("csv", encoding="utf-8")

        def close(self):
            return None

    monkeypatch.setattr("passport_core.cli.PassportCoreService", StubService)
    monkeypatch.setattr(
        "sys.argv",
        [
            "passport-core",
            "simulate-agency",
            "a.jpg",
            "b.jpg",
            "--pretty",
            "--csv-output",
            str(tmp_path / "out.csv"),
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["passport_image_uri"] == "orig://1"
    assert payload[0]["face_crop_uri"] == "faces://1"
    assert payload[0]["data"]["PassportNumber"] == "A123"
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "csv"


def test_cli_crop_face_outputs_metadata(monkeypatch, capsys):
    crop = FaceCropResult(
        bbox_original=BoundingBox(x=1, y=2, width=3, height=4, score=0.9),
        width=3,
        height=4,
        jpeg_bytes=b"jpeg",
        stored_uri="faces://1",
    )

    class StubService:
        def __init__(self, settings=None) -> None:
            self.settings = settings

        def crop_face(self, source):
            assert source == "a.jpg"
            return crop

        def close(self):
            return None

    monkeypatch.setattr("passport_core.cli.PassportCoreService", StubService)
    monkeypatch.setattr("sys.argv", ["passport-core", "crop-face", "a.jpg"])

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["stored_uri"] == "faces://1"
    assert "jpeg_bytes" not in payload


def test_collect_image_sources_filters_and_sorts(tmp_path: Path):
    (tmp_path / "b.jpeg").write_bytes(b"x")
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")

    sources = _collect_image_sources(tmp_path, recursive=False)

    assert sources == [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpeg")]


def test_cli_process_dir_outputs_batch(monkeypatch, capsys, tmp_path: Path):
    input_dir = tmp_path / "agency-input"
    input_dir.mkdir()
    (input_dir / "b.jpeg").write_bytes(b"x")
    (input_dir / "a.jpg").write_bytes(b"x")

    result = PassportProcessingResult(
        source=str(input_dir / "a.jpg"),
        trace_id="trace-1",
        passport_image_uri="orig://1",
        face_crop_uri="faces://1",
        data=PassportData(PassportNumber="A123"),
    )

    class StubService:
        def __init__(self, settings=None) -> None:
            self.settings = settings

        def process_sources(self, sources):
            assert sources == [str(input_dir / "a.jpg"), str(input_dir / "b.jpeg")]
            return [result]

        def export_results_csv(self, results, output_path):
            output_path.write_text("csv", encoding="utf-8")

        def close(self):
            return None

    monkeypatch.setattr("passport_core.cli.PassportCoreService", StubService)
    monkeypatch.setattr(
        "sys.argv",
        [
            "passport-core",
            "process-dir",
            str(input_dir),
            "--pretty",
            "--csv-output",
            str(tmp_path / "out.csv"),
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["passport_image_uri"] == "orig://1"
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "csv"
