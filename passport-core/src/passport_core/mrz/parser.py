"""MRZ (Machine Readable Zone) parsing and check digit validation for TD3 passports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_WEIGHTS = (7, 3, 1)
_CHAR_VALUES: dict[str, int] = {str(i): i for i in range(10)}
_CHAR_VALUES.update({chr(c): c - 55 for c in range(ord("A"), ord("Z") + 1)})
_CHAR_VALUES["<"] = 0
_MRZ_NAME_CLEANUP = re.compile(r"[^A-Z0-9<]")


def check_digit(s: str) -> int:
    """Compute a single MRZ check digit over *s*."""
    total = 0
    for i, ch in enumerate(s):
        total += _CHAR_VALUES.get(ch, 0) * _WEIGHTS[i % 3]
    return total % 10


def _ddmmyyyy_to_yymmdd(value: str | None) -> str | None:
    """Convert ``DD/MM/YYYY`` date string to MRZ ``YYMMDD`` format."""
    if value is None:
        return None
    parts = value.split("/")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return None
    dd, mm, yyyy = parts
    if len(dd) != 2 or len(mm) != 2 or len(yyyy) != 4:
        return None
    return f"{yyyy[-2:]}{mm}{dd}"


def _normalize_name_for_mrz(value: str) -> str:
    """Strip non-MRZ characters and uppercase a VIZ name for MRZ comparison."""
    normalized = value.upper().strip()
    normalized = normalized.replace("<", "")
    return _MRZ_NAME_CLEANUP.sub("", normalized)


def normalize_authority_mrz_name_part(value: str | None) -> str | None:
    """Normalize one VIZ name part to the issuing authority's MRZ style."""
    if value is None:
        return None
    return _normalize_name_for_mrz(value)


def normalize_authority_mrz_tokens(values: list[str] | None) -> list[str] | None:
    """Normalize ordered VIZ given-name tokens to the authority's MRZ style."""
    if values is None:
        return None
    normalized = [token for token in (_normalize_name_for_mrz(value) for value in values) if token]
    return normalized or None


def build_mrz_line1(
    country_code: str | None,
    surname_en: str | None,
    given_name_tokens_en: list[str] | None,
) -> str | None:
    """Rebuild MRZ line 1 from VIZ fields for cross-validation."""
    if not country_code or not surname_en or not given_name_tokens_en:
        return None

    surname = _normalize_name_for_mrz(surname_en)
    given = "<".join(_normalize_name_for_mrz(token) for token in given_name_tokens_en if token)
    line = f"P<{country_code.upper()[:3]}{surname}<<{given}"
    return (line[:44]).ljust(44, "<")


def build_mrz_line2(
    passport_number: str | None,
    country_code: str | None,
    date_of_birth: str | None,
    sex: str | None,
    date_of_expiry: str | None,
) -> str | None:
    """Rebuild MRZ line 2 from VIZ fields with computed check digits."""
    if (
        not passport_number
        or not country_code
        or not date_of_birth
        or not sex
        or not date_of_expiry
    ):
        return None

    passport_core = _normalize_name_for_mrz(passport_number)[:9].ljust(9, "<")
    dob = _ddmmyyyy_to_yymmdd(date_of_birth)
    expiry = _ddmmyyyy_to_yymmdd(date_of_expiry)
    sex = sex.upper()
    if dob is None or expiry is None or sex not in {"M", "F"}:
        return None

    nationality = country_code.upper()[:3]
    optional_data = "<" * 14
    passport_check = str(check_digit(passport_core))
    dob_check = str(check_digit(dob))
    expiry_check = str(check_digit(expiry))
    optional_check = str(check_digit(optional_data))
    line_without_overall = (
        passport_core
        + passport_check
        + nationality
        + dob
        + dob_check
        + sex
        + expiry
        + expiry_check
        + optional_data
        + optional_check
    )
    overall_composite = (
        passport_core
        + passport_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + optional_data
        + optional_check
    )
    overall_check = str(check_digit(overall_composite))
    return line_without_overall + overall_check


def _yymmdd_to_ddmmyyyy(yymmdd: str, *, pivot: int = 30) -> str | None:
    """Convert MRZ ``YYMMDD`` to ``DD/MM/YYYY``.

    Years below *pivot* map to 20xx, otherwise 19xx.
    """
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    yy, mm, dd = int(yymmdd[:2]), yymmdd[2:4], yymmdd[4:6]
    century = 2000 if yy < pivot else 1900
    return f"{dd}/{mm}/{century + yy}"


@dataclass
class CheckDigitResult:
    name: str
    expected: int
    computed: int

    @property
    def ok(self) -> bool:
        return self.expected == self.computed


@dataclass
class MrzParsed:
    """Structured output from :func:`parse_mrz`."""

    valid: bool = False
    passport_number: str | None = None
    country_code: str | None = None
    dob: str | None = None
    sex: str | None = None
    expiry: str | None = None
    surname: str | None = None
    given_names: str | None = None
    checks: list[CheckDigitResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_mrz(line1: str | None, line2: str | None) -> MrzParsed:
    """Parse TD3 MRZ lines and validate check digits."""
    result = MrzParsed()

    if not line1 and not line2:
        result.warnings.append("MRZ lines missing or incomplete")
        return result

    if line1:
        line1 = line1.replace(" ", "").upper()
        if len(line1) != 44:
            result.warnings.append(f"MRZ line 1 length is {len(line1)}, expected 44")

        if len(line1) >= 44:
            result.country_code = line1[2:5].replace("<", "")
            name_section = line1[5:44]
            parts = name_section.split("<<", 1)
            result.surname = parts[0].replace("<", " ").strip() if parts else None
            if len(parts) > 1:
                result.given_names = parts[1].replace("<", " ").strip()

    if not line2:
        result.warnings.append("MRZ line 2 missing")
        return result

    line2 = line2.replace(" ", "").upper()
    if len(line2) != 44:
        result.warnings.append(f"MRZ line 2 length is {len(line2)}, expected 44")

    if len(line2) < 44:
        return result

    raw_pn = line2[0:9]
    result.passport_number = raw_pn.replace("<", "").strip()

    if line2[9].isdigit():
        result.checks.append(
            CheckDigitResult("passport_number", int(line2[9]), check_digit(raw_pn))
        )

    raw_dob = line2[13:19]
    result.dob = _yymmdd_to_ddmmyyyy(raw_dob, pivot=30)
    if line2[19].isdigit():
        result.checks.append(CheckDigitResult("dob", int(line2[19]), check_digit(raw_dob)))

    result.sex = line2[20] if line2[20] in ("M", "F") else None

    raw_exp = line2[21:27]
    result.expiry = _yymmdd_to_ddmmyyyy(raw_exp, pivot=70)
    if line2[27].isdigit():
        result.checks.append(CheckDigitResult("expiry", int(line2[27]), check_digit(raw_exp)))

    raw_optional = line2[28:42]
    if line2[42].isdigit():
        result.checks.append(
            CheckDigitResult("optional_data", int(line2[42]), check_digit(raw_optional))
        )

    composite = line2[0:10] + line2[13:20] + line2[21:43]
    if line2[43].isdigit():
        result.checks.append(CheckDigitResult("overall", int(line2[43]), check_digit(composite)))

    result.valid = all(c.ok for c in result.checks)
    if not result.valid:
        failed = [c.name for c in result.checks if not c.ok]
        result.warnings.append(f"Check digit failures: {', '.join(failed)}")

    return result


def validate_mrz(line2: str | None) -> tuple[bool, list[str]]:
    """Quick validation of MRZ line 2 check digits.

    Returns ``(all_pass, [warning_strings])``.
    """
    if not line2:
        return False, ["MRZ line 2 missing"]

    line2 = line2.replace(" ", "").upper()
    if len(line2) < 44:
        return False, [f"MRZ line 2 length is {len(line2)}, expected 44"]

    warnings: list[str] = []
    checks: list[CheckDigitResult] = []

    if line2[9].isdigit():
        checks.append(CheckDigitResult("passport_number", int(line2[9]), check_digit(line2[0:9])))
    if line2[19].isdigit():
        checks.append(CheckDigitResult("dob", int(line2[19]), check_digit(line2[13:19])))
    if line2[27].isdigit():
        checks.append(CheckDigitResult("expiry", int(line2[27]), check_digit(line2[21:27])))
    if line2[42].isdigit():
        checks.append(CheckDigitResult("optional_data", int(line2[42]), check_digit(line2[28:42])))

    composite = line2[0:10] + line2[13:20] + line2[21:43]
    if line2[43].isdigit():
        checks.append(CheckDigitResult("overall", int(line2[43]), check_digit(composite)))

    all_pass = all(c.ok for c in checks)
    if not all_pass:
        failed = [c.name for c in checks if not c.ok]
        warnings.append(f"Check digit failures: {', '.join(failed)}")

    return all_pass, warnings
