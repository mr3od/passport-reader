"""MRZ (Machine Readable Zone) parsing and validation for TD3 passports."""

from passport_core.mrz.parser import (
    CheckDigitResult,
    MrzParsed,
    build_mrz_line1,
    build_mrz_line2,
    check_digit,
    normalize_authority_mrz_name_part,
    normalize_authority_mrz_tokens,
    parse_mrz,
    validate_mrz,
)

__all__ = [
    "CheckDigitResult",
    "MrzParsed",
    "build_mrz_line1",
    "build_mrz_line2",
    "check_digit",
    "normalize_authority_mrz_name_part",
    "normalize_authority_mrz_tokens",
    "parse_mrz",
    "validate_mrz",
]
