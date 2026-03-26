from __future__ import annotations

from pathlib import Path

from passport_core.config import Settings


def test_relative_asset_overrides_preserve_subdirectories(monkeypatch):
    monkeypatch.delenv("PASSPORT_ASSETS_DIR", raising=False)
    monkeypatch.delenv("PASSPORT_TEMPLATE_PATH", raising=False)
    monkeypatch.delenv("PASSPORT_FACE_MODEL_PATH", raising=False)
    settings = Settings(
        assets_dir=Path("assets"),
        template_path=Path("templates/custom/template.jpg"),
        face_model_path=Path("models/custom/retinaface.onnx"),
    )

    assert settings.template_path == Path("assets/templates/custom/template.jpg")
    assert settings.face_model_path == Path("assets/models/custom/retinaface.onnx")


def test_default_asset_paths_are_not_prefixed_twice(monkeypatch):
    monkeypatch.setenv("PASSPORT_ASSETS_DIR", "passport-core/assets")
    monkeypatch.delenv("PASSPORT_TEMPLATE_PATH", raising=False)
    monkeypatch.delenv("PASSPORT_FACE_MODEL_PATH", raising=False)
    settings = Settings()

    assert settings.template_path == Path("passport-core/assets/passport_template_v2.jpg")
    assert settings.face_model_path == Path(
        "passport-core/assets/face_detection_retinaface_mobile0.25.onnx"
    )
