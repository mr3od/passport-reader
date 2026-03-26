"""Passport extraction benchmark and evaluation suite."""

from __future__ import annotations

__version__ = "0.2.0"

from passport_core.mrz import parse_mrz, validate_mrz

from passport_benchmark.compare import evaluate_case
from passport_benchmark.runner import run_benchmark

__all__ = [
    "evaluate_case",
    "parse_mrz",
    "run_benchmark",
    "validate_mrz",
]
