"""Programmatic confidence scoring from image metadata and cross-validation."""

from __future__ import annotations

from passport_core.extraction.models import Confidence, ImageMeta, PassportFields


def compute_confidence(
    data: PassportFields,
    meta: ImageMeta | None,
    warnings: list[str],
) -> Confidence:
    """Compute confidence programmatically from image metadata and cross-validation.

    Starts every field at 1.0 and applies penalty caps based on:
    1. Image properties (orientation, quality, mirroring, skew)
    2. Cross-validation warnings (MRZ vs VIZ discrepancies, check digit failures)
    3. Field presence (null fields get 0.0)
    """
    all_field_names = set(PassportFields.model_fields)
    mrz_fields = {"PassportNumber", "MrzLine1", "MrzLine2", "DateOfBirth", "DateOfExpiry", "Sex"}

    fields = {f: 1.0 for f in all_field_names}

    def _cap(field_names: set[str], cap: float) -> None:
        for f in field_names:
            fields[f] = min(fields[f], cap)

    # ── Image metadata penalties ──
    if meta is not None:
        if meta.mirrored is True:
            _cap(all_field_names, 0.35)

        orientation_caps = {"rotated_90": 0.7, "rotated_180": 0.7, "rotated_270": 0.7}
        orientation_cap = orientation_caps.get(meta.orientation or "")
        if orientation_cap is not None:
            _cap(all_field_names, orientation_cap)
            _cap(mrz_fields, 0.6)

        skew_caps = {"mild": 0.85, "severe": 0.6}
        skew_cap = skew_caps.get(meta.skew_level or "")
        if skew_cap is not None:
            _cap(all_field_names, skew_cap)

        quality_caps = {"fair": 0.9, "poor": 0.65}
        quality_cap = quality_caps.get(meta.image_quality or "")
        if quality_cap is not None:
            _cap(all_field_names, quality_cap)

    # ── Cross-validation warning penalties ──
    for warning in warnings:
        if warning.startswith("Check digit failures"):
            _cap(mrz_fields, 0.3)
        elif warning.startswith("PassportNumber:"):
            _cap({"PassportNumber", "MrzLine2"}, 0.2)
        elif warning.startswith("DOB:"):
            _cap({"DateOfBirth", "MrzLine2"}, 0.2)
        elif warning.startswith("Expiry:"):
            _cap({"DateOfExpiry", "MrzLine2"}, 0.2)
        elif warning.startswith("Sex:"):
            _cap({"Sex", "MrzLine2"}, 0.2)
        elif warning.startswith("Given name tokens:"):
            _cap({"GivenNameTokensAr", "GivenNameTokensEn"}, 0.4)
        elif warning.startswith("SurnameEn:"):
            _cap({"SurnameEn", "MrzLine1"}, 0.4)
        elif warning.startswith("GivenNameTokensEn:"):
            _cap({"GivenNameTokensEn", "MrzLine1"}, 0.4)
        elif "rebuild mismatch" in warning:
            if "MrzLine1" in warning:
                _cap({"MrzLine1"}, 0.5)
            elif "MrzLine2" in warning:
                _cap({"MrzLine2"}, 0.5)

    # ── Null field penalty: no value = no confidence ──
    for field_name in all_field_names:
        value = getattr(data, field_name)
        if value is None or (isinstance(value, list) and not value):
            fields[field_name] = 0.0

    overall = sum(v for v in fields.values() if v > 0.0)
    non_null_count = sum(1 for v in fields.values() if v > 0.0)
    overall = overall / non_null_count if non_null_count else 0.0

    return Confidence(overall=overall, fields=fields)
