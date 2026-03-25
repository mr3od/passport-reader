"""Cross-validation of extracted fields against MRZ data."""

from __future__ import annotations

from typing import cast

from passport_core.mrz import (
    build_mrz_line1,
    build_mrz_line2,
    normalize_authority_mrz_name_part,
    normalize_authority_mrz_tokens,
    parse_mrz,
)


def _authority_mrz_tokens_match(
    mrz_tokens: list[str],
    viz_tokens: list[str],
    *,
    allow_final_truncation: bool = False,
) -> bool:
    normalized_mrz = normalize_authority_mrz_tokens(mrz_tokens)
    normalized_viz = normalize_authority_mrz_tokens(viz_tokens)
    if not normalized_mrz or not normalized_viz:
        return normalized_mrz == normalized_viz
    if len(normalized_mrz) != len(normalized_viz):
        return False
    for index, (mrz_token, viz_token) in enumerate(
        zip(normalized_mrz, normalized_viz, strict=True)
    ):
        is_last = index == len(normalized_mrz) - 1
        if mrz_token == viz_token:
            continue
        if allow_final_truncation and is_last and viz_token.startswith(mrz_token):
            continue
        return False
    return True


def _append_given_name_token_range_warnings(warnings: list[str], actual: dict) -> None:
    """Warn when Arabic or English given-name token counts fall outside 3-4."""
    for field_name, label in (
        ("GivenNameTokensAr", "Arabic"),
        ("GivenNameTokensEn", "English"),
    ):
        tokens = actual.get(field_name)
        if not isinstance(tokens, list):
            continue
        token_count = len(tokens)
        if 3 <= token_count <= 4:
            continue
        warnings.append(
            f"Given name token count out of range: {label}={token_count} (expected 3-4)"
        )


def cross_validate(actual: dict) -> list[str]:
    """Run programmatic MRZ cross-validation on extractor output.

    Compares MRZ-parsed fields against VIZ-extracted fields and returns warnings.
    """
    warnings: list[str] = []
    actual_mrz1 = actual.get("MrzLine1")
    actual_mrz2 = actual.get("MrzLine2")
    mrz = parse_mrz(actual_mrz1, actual_mrz2)
    warnings.extend(mrz.warnings)

    if (
        mrz.passport_number
        and actual.get("PassportNumber")
        and mrz.passport_number != actual["PassportNumber"]
    ):
        warnings.append(
            f"PassportNumber: MRZ='{mrz.passport_number}' vs VIZ='{actual['PassportNumber']}'"
        )

    if mrz.dob and actual.get("DateOfBirth") and mrz.dob != actual["DateOfBirth"]:
        warnings.append(f"DOB: MRZ='{mrz.dob}' vs VIZ='{actual['DateOfBirth']}'")

    if mrz.expiry and actual.get("DateOfExpiry") and mrz.expiry != actual["DateOfExpiry"]:
        warnings.append(f"Expiry: MRZ='{mrz.expiry}' vs VIZ='{actual['DateOfExpiry']}'")

    if mrz.sex and actual.get("Sex") and mrz.sex != actual["Sex"]:
        warnings.append(f"Sex: MRZ='{mrz.sex}' vs VIZ='{actual['Sex']}'")

    if mrz.surname and actual.get("SurnameEn"):
        normalized_mrz_surname = normalize_authority_mrz_name_part(mrz.surname)
        normalized_viz_surname = normalize_authority_mrz_name_part(actual["SurnameEn"])
        if normalized_mrz_surname != normalized_viz_surname:
            warnings.append(f"SurnameEn: MRZ='{mrz.surname}' vs VIZ='{actual['SurnameEn']}'")

    mrz_given_tokens = [token for token in (mrz.given_names or "").split() if token]
    viz_given_tokens = actual.get("GivenNameTokensEn")
    if (
        mrz_given_tokens
        and isinstance(viz_given_tokens, list)
        and not _authority_mrz_tokens_match(
            cast(list[str], mrz_given_tokens),
            cast(list[str], viz_given_tokens),
            allow_final_truncation=True,
        )
    ):
        warnings.append(f"GivenNameTokensEn: MRZ={mrz_given_tokens} vs VIZ={viz_given_tokens}")

    ar = actual.get("GivenNameTokensAr")
    en = actual.get("GivenNameTokensEn")
    if isinstance(ar, list) and isinstance(en, list) and len(ar) != len(en):
        warnings.append(f"Given name tokens: Arabic={len(ar)} vs English={len(en)}")
    _append_given_name_token_range_warnings(warnings, actual)

    rebuilt_mrz1 = build_mrz_line1(
        actual.get("CountryCode"),
        actual.get("SurnameEn"),
        actual.get("GivenNameTokensEn"),
    )
    if rebuilt_mrz1 and actual_mrz1 and rebuilt_mrz1 != actual_mrz1:
        warnings.append(
            f"MrzLine1 rebuild mismatch: expected='{rebuilt_mrz1}' actual='{actual_mrz1}'"
        )

    rebuilt_mrz2 = build_mrz_line2(
        actual.get("PassportNumber"),
        actual.get("CountryCode"),
        actual.get("DateOfBirth"),
        actual.get("Sex"),
        actual.get("DateOfExpiry"),
    )
    if rebuilt_mrz2 and actual_mrz2 and rebuilt_mrz2 != actual_mrz2:
        warnings.append(
            f"MrzLine2 rebuild mismatch: expected='{rebuilt_mrz2}' actual='{actual_mrz2}'"
        )

    return warnings
