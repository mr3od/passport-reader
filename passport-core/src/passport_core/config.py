from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_",
        env_file=".env",
        extra="ignore",
    )

    assets_dir: Path = Path("assets")
    template_path: Path = Path("assets/passport_template_v2.jpg")
    face_model_path: Path = Path("assets/face_detection_yunet_2023mar.onnx")

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

    face_score_threshold: float = 0.60

    llm_model: str = "openai-responses/gpt-5-mini"
    requesty_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    requesty_base_url: str = "https://router.requesty.ai/v1"
    log_level: str = "INFO"
    log_json: bool = False
