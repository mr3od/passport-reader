from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def sample_bgr_image() -> np.ndarray:
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (40, 30), (560, 370), (255, 255, 255), 2)
    cv2.rectangle(img, (50, 50), (200, 250), (200, 200, 200), -1)
    cv2.line(img, (50, 300), (550, 300), (180, 180, 180), 2)
    cv2.line(img, (50, 330), (550, 330), (180, 180, 180), 2)
    cv2.putText(img, "PASSPORT", (220, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, "P<YEM", (60, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return img


@pytest.fixture()
def sample_jpeg_bytes(sample_bgr_image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", sample_bgr_image)
    assert ok
    return buf.tobytes()


@pytest.fixture()
def reference_template_path(tmp_path: Path, sample_bgr_image: np.ndarray) -> Path:
    p = tmp_path / "passport_template_v2.jpg"
    cv2.imwrite(str(p), sample_bgr_image)
    return p
