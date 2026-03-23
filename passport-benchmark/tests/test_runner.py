from __future__ import annotations

from pathlib import Path

from passport_benchmark.runner import _resolve_run_dir, _sanitize_run_id


class TestRunIds:
    def test_sanitize_run_id(self):
        assert _sanitize_run_id("gpt 5 / mrz fix") == "gpt-5-mrz-fix"

    def test_resolve_explicit_run_id(self, tmp_path: Path):
        cases_dir = tmp_path / "cases"
        run_dir, run_id = _resolve_run_dir(
            cases_dir,
            "my run",
            extract=False,
            model="ignored",
        )

        assert run_id == "my-run"
        assert run_dir == tmp_path / "runs" / "my-run"

    def test_resolve_latest_run_id_for_scoring(self, tmp_path: Path):
        cases_dir = tmp_path / "cases"
        runs_dir = tmp_path / "runs"
        first = runs_dir / "first"
        second = runs_dir / "second"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        (first / "metadata.json").write_text("{}\n")
        (second / "metadata.json").write_text("{}\n")

        run_dir, run_id = _resolve_run_dir(
            cases_dir,
            None,
            extract=False,
            model="ignored",
        )

        assert run_dir is not None
        assert run_id == run_dir.name
