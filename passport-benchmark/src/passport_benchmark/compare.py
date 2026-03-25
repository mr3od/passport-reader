"""Field-level comparison with Arabic-aware normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from passport_core.mrz import (
    build_mrz_line1,
    build_mrz_line2,
    normalize_authority_mrz_name_part,
    normalize_authority_mrz_tokens,
    parse_mrz,
    validate_mrz,
)

if TYPE_CHECKING:
    pass

# ── Field taxonomy ───────────────────────────────────────────────

FIELD_GROUPS: dict[str, list[str]] = {
    "identifiers": ["PassportNumber", "CountryCode"],
    "mrz": ["MrzLine1", "MrzLine2"],
    "names_ar": [
        "SurnameAr",
        "GivenNameTokensAr",
    ],
    "names_en": [
        "SurnameEn",
        "GivenNameTokensEn",
    ],
    "dates": ["DateOfBirth", "DateOfIssue", "DateOfExpiry"],
    "demographics": ["Sex"],
    "places_ar": ["PlaceOfBirthAr", "BirthCityAr", "BirthCountryAr"],
    "places_en": ["PlaceOfBirthEn", "BirthCityEn", "BirthCountryEn"],
    "profession": ["ProfessionAr", "ProfessionEn"],
    "authority": ["IssuingAuthorityAr", "IssuingAuthorityEn"],
}

ALL_FIELDS: list[str] = [f for fields in FIELD_GROUPS.values() for f in fields]

FIELD_TO_GROUP: dict[str, str] = {}
for _group, _fields in FIELD_GROUPS.items():
    for _f in _fields:
        FIELD_TO_GROUP[_f] = _group


# ── Normalization ────────────────────────────────────────────────


def normalize_arabic(s: str) -> str:
    """Normalize Arabic text for *comparison only* (not for display)."""
    s = s.strip()
    s = re.sub(r"[إأآ]", "ا", s)  # alef variants → bare alef
    s = re.sub(r"[\u064B-\u065F\u0670]", "", s)  # strip tashkeel
    s = s.replace("ة", "ه")  # taa marbuta → haa
    s = s.replace("ى", "ي")  # alef maqsura → yaa
    return re.sub(r"\s+", " ", s).strip()


def normalize_english(s: str) -> str:
    """Normalize English text for comparison."""
    s = s.strip().upper()
    s = s.replace("-", " ").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()


def normalize_mrz_semantic(field_name: str, s: str) -> str:
    """Normalize MRZ for semantic comparison without hiding raw format errors."""
    s = s.replace(" ", "").upper().strip()
    if field_name == "MrzLine1":
        if len(s) <= 5:
            return s
        return s[:5] + s[5:].rstrip("<")

    if field_name == "MrzLine2":
        if len(s) <= 30:
            return s.rstrip("<")
        prefix = s[:28]
        optional_and_checks = s[28:]
        if len(optional_and_checks) <= 2:
            return prefix + optional_and_checks
        optional_data = optional_and_checks[:-2].rstrip("<")
        trailing_checks = optional_and_checks[-2:]
        return prefix + optional_data + "|" + trailing_checks

    return s


def semantic_mrz_match(field_name: str, expected: str | None, actual: str | None) -> bool:
    """Compare MRZ lines semantically while keeping strict raw scoring separate."""
    if expected is None or actual is None:
        return False
    return normalize_mrz_semantic(field_name, expected) == normalize_mrz_semantic(
        field_name,
        actual,
    )


def _token_lists_match(
    expected: list[str],
    actual: list[str],
    normalizer,
) -> bool:
    if len(expected) != len(actual):
        return False
    return all(
        normalizer(exp) == normalizer(act) for exp, act in zip(expected, actual, strict=True)
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


def fields_match(field_name: str, expected: str | list[str], actual: str | list[str]) -> bool:
    """Compare two field values with type-aware normalization."""
    if field_name == "GivenNameTokensAr":
        return (
            isinstance(expected, list)
            and isinstance(actual, list)
            and _token_lists_match(expected, actual, normalize_arabic)
        )
    if field_name == "GivenNameTokensEn":
        return (
            isinstance(expected, list)
            and isinstance(actual, list)
            and _token_lists_match(expected, actual, normalize_english)
        )
    if field_name.endswith("Ar"):
        assert isinstance(expected, str) and isinstance(actual, str)
        return normalize_arabic(expected) == normalize_arabic(actual)
    if field_name in ("MrzLine1", "MrzLine2"):
        assert isinstance(expected, str) and isinstance(actual, str)
        return expected.rstrip("<") == actual.rstrip("<")
    assert isinstance(expected, str) and isinstance(actual, str)
    return normalize_english(expected) == normalize_english(actual)


# ── Results ──────────────────────────────────────────────────────


@dataclass
class FieldResult:
    """Comparison result for a single field."""

    field_name: str
    field_group: str
    expected: object | None
    actual: object | None
    status: str  # match | misread | hallucination | omission | both_null


@dataclass
class CaseResult:
    """Aggregated comparison result for one benchmark case."""

    case_id: str
    meta: dict = field(default_factory=dict)
    fields: list[FieldResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mrz_valid: bool | None = None

    @property
    def scorable(self) -> list[FieldResult]:
        return [f for f in self.fields if f.status != "both_null"]

    @property
    def accuracy(self) -> float:
        s = self.scorable
        if not s:
            return 1.0
        return sum(1 for f in s if f.status == "match") / len(s)

    def error_counts(self) -> dict[str, int]:
        return {
            "hallucination": sum(1 for f in self.fields if f.status == "hallucination"),
            "omission": sum(1 for f in self.fields if f.status == "omission"),
            "misread": sum(1 for f in self.fields if f.status == "misread"),
        }

    def group_accuracy(self) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for group, names in FIELD_GROUPS.items():
            scored = [f for f in self.fields if f.field_name in names and f.status != "both_null"]
            result[group] = (
                (sum(1 for f in scored if f.status == "match") / len(scored)) if scored else None
            )
        return result


# ── Evaluation ───────────────────────────────────────────────────


def _normalize_field_value(value: object | None) -> object | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        normalized = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return normalized or None
    return value


def _compare_field(field_name: str, expected: object | None, actual: object | None) -> FieldResult:
    exp = _normalize_field_value(expected)
    act = _normalize_field_value(actual)
    group = FIELD_TO_GROUP.get(field_name, "other")

    if exp is None and act is None:
        status = "both_null"
    elif exp is None and act is not None:
        status = "hallucination"
    elif exp is not None and act is None:
        status = "omission"
    elif (isinstance(exp, str) and isinstance(act, str) and fields_match(field_name, exp, act)) or (
        isinstance(exp, list)
        and all(isinstance(item, str) for item in exp)
        and isinstance(act, list)
        and all(isinstance(item, str) for item in act)
        and fields_match(field_name, cast(list[str], exp), cast(list[str], act))
    ):
        status = "match"
    else:
        status = "misread"

    return FieldResult(
        field_name=field_name,
        field_group=group,
        expected=exp,
        actual=act,
        status=status,
    )


def _apply_semantic_place_results(result: CaseResult) -> None:
    """Score composite birthplace fields from the authoritative atomic fields.

    ``PlaceOfBirthAr`` is retained for debugging, but its scored status should
    follow the normalized ``BirthCountryAr`` and ``BirthCityAr`` fields rather
    than exact display formatting like ordering or separators.
    """
    field_by_name = {field.field_name: field for field in result.fields}
    place = field_by_name.get("PlaceOfBirthAr")
    country = field_by_name.get("BirthCountryAr")
    city = field_by_name.get("BirthCityAr")
    if place is None or country is None or city is None:
        return
    if place.status in {"both_null", "hallucination", "omission"}:
        return

    if country.status == "match" and city.status == "match":
        place.status = "match"
    else:
        place.status = "misread"


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

    # Name token count check (Arabic vs English)
    ar = actual.get("GivenNameTokensAr")
    en = actual.get("GivenNameTokensEn")
    if isinstance(ar, list) and isinstance(en, list):
        ar_count = len(ar)
        en_count = len(en)
        if ar_count != en_count:
            warnings.append(f"Given name tokens: Arabic={ar_count} vs English={en_count}")
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


def evaluate_case(
    case_id: str,
    expected: dict,
    actual: dict,
    *,
    meta: dict | None = None,
) -> CaseResult:
    """Compare actual extractor output against ground truth for one case."""
    result = CaseResult(case_id=case_id, meta=meta or expected.get("_meta", {}))

    for f in ALL_FIELDS:
        result.fields.append(_compare_field(f, expected.get(f), actual.get(f)))

    _apply_semantic_place_results(result)

    # MRZ validation on actual output
    actual_mrz2 = actual.get("MrzLine2")
    if actual_mrz2:
        ok, mrz_warnings = validate_mrz(actual_mrz2)
        result.mrz_valid = ok
        result.warnings.extend(mrz_warnings)

    return result
