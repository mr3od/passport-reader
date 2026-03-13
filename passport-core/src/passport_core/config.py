from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_",
        env_file=".env",
        extra="ignore",
    )

    assets_dir: Path = Path("assets")
    template_path: Path = Path("assets/passport_template_v2.jpg")
    face_model_path: Path = Path("assets/face_detection_retinaface_mobile0.25.onnx")

    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: Path = Path("data")
    s3_bucket: str | None = None
    s3_prefix: str = "passport-core"

    data_store_backend: Literal["json", "csv", "sqlite"] = "sqlite"
    data_store_path: Path = Path("data")

    http_timeout_seconds: float = 30.0
    max_download_bytes: int = 15 * 1024 * 1024

    validator_sift_features: int = 0
    validator_ratio_test: float = 0.75
    validator_flann_trees: int = 5
    validator_flann_checks: int = 64
    validator_min_good_matches: int = 100
    validator_min_inliers: int = 80
    validator_min_inlier_ratio: float = 0.22
    validator_ransac_threshold: float = 5.0
    validator_min_quad_area_ratio: float = 0.01
    validator_max_quad_area_ratio: float = 4.0

    face_score_threshold: float = 0.60
    face_nms_threshold: float = 0.40
    face_input_width: int = 640
    face_input_height: int = 640

    candidate_early_stop_validation_score: float = 50.0
    candidate_early_stop_face_score: float = 0.85
    candidate_early_stop_landmark_score: float = 0.75
    candidate_max_extraction_attempts: int = 2

    llm_model: str = "openai-responses/gpt-5-mini"
    requesty_api_key: SecretStr | None = None
    requesty_base_url: str = "https://router.requesty.ai/v1"
    log_level: str = "INFO"
    log_json: bool = False

    @model_validator(mode="after")
    def _resolve_asset_paths(self) -> Settings:
        if (
            not self.template_path.is_absolute()
            and not self._is_under_assets_dir(self.template_path)
        ):
            self.template_path = self.assets_dir / self.template_path
        if not self.face_model_path.is_absolute() and not self._is_under_assets_dir(
            self.face_model_path
        ):
            self.face_model_path = self.assets_dir / self.face_model_path
        return self

    def _is_under_assets_dir(self, path: Path) -> bool:
        return len(path.parts) > 0 and path.parts[0] == self.assets_dir.name
