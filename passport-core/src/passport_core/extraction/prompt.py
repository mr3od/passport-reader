"""Multi-step passport extraction prompt for VLM-based extraction."""

from __future__ import annotations

EXTRACTION_PROMPT = """
You extract fields from a single passport image using a strict multi-step process.
You MUST output your reasoning for each step before producing the final JSON.

═══════════════════════════════════════════════════════════════════
STEP 1 — IMAGE ASSESSMENT
═══════════════════════════════════════════════════════════════════

Before extracting anything, describe:
1. Is this a passport? (If not, stop and return all nulls.)
2. Orientation: normal, rotated_90, rotated_180, rotated_270?
3. Layout: single data page / two-page spread / passport on A4 sheet?
   - Two-page spread: the data page is the RIGHT or BOTTOM page.
   - A4 scanned sheet: ignore margins and background.
4. Image type: photographed (handheld/angle) or scanned (flatbed)?
5. Quality: good / fair / poor? Note any obstructions (fingers, glare, tape, stamps).
6. Is the image mirrored/flipped? mirrored = true/false.
7. Is there geometric skew/perspective distortion? skew_level = none / mild / severe.

Important for transformed images:
- A horizontally flipped or mirrored passport is still a passport. Do not reject it.
- Report mirroring separately from rotation.
- If the image is rotated and mirrored, set both fields accordingly.

═══════════════════════════════════════════════════════════════════
STEP 2 — STRUCTURED DATA EXTRACTION (machine-readable fields)
═══════════════════════════════════════════════════════════════════

Extract these fields which have strict formats:
- PassportNumber (numeric, from the PASSPORT NO field)
- CountryCode (3-letter, from COUNTRY CODE field)
- DateOfBirth (DD/MM/YYYY from the English DATE OF BIRTH field)
- DateOfIssue (DD/MM/YYYY from the English DATE OF ISSUE field)
- DateOfExpiry (DD/MM/YYYY from the English DATE OF EXPIRY field)
- Sex ("M" or "F" from the English SEX field)

═══════════════════════════════════════════════════════════════════
STEP 3 — ARABIC FIELD EXTRACTION (from VIZ only)
═══════════════════════════════════════════════════════════════════

Read the ARABIC text on the RIGHT side of the data page. These fields do NOT
appear in the MRZ, so the Arabic VIZ is the only source. Extract exactly what
is printed — do NOT translate from the English side.

- SurnameAr (اللقب field)
- GivenNameTokensAr (array of given-name tokens in order, from الاسم field)
- ProfessionAr (المهنة field)
- PlaceOfBirthAr (محل الميلاد field — full string as printed)
- BirthCityAr (city/district part only, without country)
- BirthCountryAr (country part only)
- IssuingAuthorityAr (جهة الإصدار field)

Arabic compound name rules:
- عبدالله is ONE token (not عبد الله). Same for عبدالرحمن, عبدالحكيم, عبدالعزيز, etc.
  Merge only when the second part is a divine/known compound element.
- "عبد" alone (without a following divine name) is a valid standalone token — do NOT merge.
- Separate name tokens are separated by spaces: "عمر عبدالحكيم حزام" = 3 tokens.

CRITICAL — Do NOT back-translate from English:
- Read the Arabic characters directly from the image.
- AL-AKBARI in English could be العكبري or الأكبري — only the Arabic image tells you which.
- Names like لناء (Lana) are valid Arabic spellings — do not "correct" to لانا.
- If Arabic text is not visible for a field, return null. Do NOT synthesize Arabic from English.

═══════════════════════════════════════════════════════════════════
STEP 4 — MRZ EXTRACTION AND PARSING
═══════════════════════════════════════════════════════════════════

Read the two MRZ lines at the bottom of the data page. Each line is exactly 44 characters.
Characters are: A-Z, 0-9, and < (filler).

Return the raw lines as MrzLine1 and MrzLine2.

Then parse them to extract cross-validation data:

MRZ LINE 1 structure (TD3 passport):
  Position 1:     Document type ("P")
  Position 2:     Type sub ("" or "<")
  Position 3-5:   Issuing country (3-letter code)
  Position 6-44:  Surname << Given<Names<Separated<By<Single<Chevrons

MRZ LINE 2 structure:
  Position 1-9:   Passport number (may include < as filler)
  Position 10:    Check digit for passport number
  Position 11-13: Nationality (3-letter code)
  Position 14-19: Date of birth (YYMMDD)
  Position 20:    Check digit for DOB
  Position 21:    Sex (M/F/< for unspecified)
  Position 22-27: Date of expiry (YYMMDD)
  Position 28:    Check digit for expiry
  Position 29-42: Personal number / optional data
  Position 43:    Check digit for personal number (or < if empty)
  Position 44:    Overall check digit

The check digits (positions 10, 20, 28, 43, 44) are computed from adjacent fields.
They are NOT part of the field values.

Parse and note:
- MRZ passport number (positions 1-9, strip trailing <)
- MRZ DOB → convert YYMMDD to DD/MM/YYYY
- MRZ sex
- MRZ expiry → convert YYMMDD to DD/MM/YYYY
- MRZ surname and given names (from line 1)

═══════════════════════════════════════════════════════════════════
STEP 5 — ENGLISH VIZ EXTRACTION
═══════════════════════════════════════════════════════════════════

Read the ENGLISH text on the LEFT/CENTER of the data page:
- SurnameEn (SURNAME field)
- GivenNameTokensEn (array of given-name tokens in order, from GIVEN NAMES field)
- ProfessionEn (PROFESSION field — extract exactly as printed, including abbreviations)
- PlaceOfBirthEn (PLACE OF BIRTH field — full string as printed)
- BirthCityEn (city/district part only)
- BirthCountryEn (country code part only, e.g. YEM, KSA)
- IssuingAuthorityEn (ISSUING AUTHORITY field)

═══════════════════════════════════════════════════════════════════
STEP 6 — MRZ vs VIZ CROSS-VALIDATION
═══════════════════════════════════════════════════════════════════

Compare Step 4 (MRZ parsed) with Step 2 (dates) and Step 5 (English names):

Signal priority when MRZ and VIZ disagree:
- DATES (DOB, expiry): prefer MRZ — machine-printed, less OCR ambiguity.
- NAMES: prefer VIZ — MRZ truncates at 44 chars and drops diacritics/hyphens.
  (e.g. MRZ says "ALAKBARI" but VIZ says "AL-AKBARI" → use VIZ)
- SEX: prefer MRZ — single unambiguous character.
- PASSPORT NUMBER: prefer MRZ — it includes a check digit for verification.
- COUNTRY CODE: prefer MRZ.

Report any discrepancies you find. If MRZ is unreadable, note this and rely on VIZ.

═══════════════════════════════════════════════════════════════════
STEP 7 — ARABIC ↔ ENGLISH CONSISTENCY CHECK
═══════════════════════════════════════════════════════════════════

Verify that Arabic and English fields are consistent:
- Name token count should match (e.g. 3 Arabic given names → 3 English given names).
- Names should be plausible transliterations of each other:
  محمد ↔ MOHAMMED, أحمد ↔ AHMED, سالم ↔ SALEM, عبدالله ↔ ABDULLAH,
  فاطمه ↔ FATIMA, عمر ↔ OMAR/OMER, etc.
- Do NOT force strict transliteration — Yemeni passports have inconsistent romanization.
  Accept: عامر ↔ AMER (not AAMER), سعيد ↔ SAEED (not SAEID), جمعان ↔ GUMAAN.

Flag if:
- An Arabic name token has no corresponding English token (or vice versa).
- The Arabic and English appear to describe different people entirely.

Do NOT:
- Change Arabic text to match English transliteration.
- Change English text to match Arabic.
- Assume Arabic spelling from English
  (e.g. don't assume الأكبري from AL-AKBARI — it may be العكبري).

═══════════════════════════════════════════════════════════════════
FINAL OUTPUT
═══════════════════════════════════════════════════════════════════

After completing all steps, return a JSON object with these keys:

_meta: {
  is_passport: true/false,
  orientation: "normal" | "rotated_90" | "rotated_180" | "rotated_270",
  image_type: "photographed" | "scanned",
  layout: "single_page" | "two_page_spread" | "passport_on_a4_sheet",
  image_quality: "good" | "fair" | "poor",
  mirrored: true/false,
  skew_level: "none" | "mild" | "severe",
  reasoning: "<short image assessment>"
}

_reasoning: {
  step1_assessment: "<your image assessment>",
  step6_mrz_viz_discrepancies: "<any conflicts found, or 'none'>",
  step7_ar_en_consistency: "<any issues found, or 'consistent'>"
}

Plus all extraction fields:
PassportNumber, CountryCode, MrzLine1, MrzLine2,
SurnameAr, GivenNameTokensAr,
SurnameEn, GivenNameTokensEn,
DateOfBirth, PlaceOfBirthAr, PlaceOfBirthEn,
BirthCityAr, BirthCityEn, BirthCountryAr, BirthCountryEn, Sex,
DateOfIssue, DateOfExpiry, ProfessionAr, ProfessionEn,
IssuingAuthorityAr, IssuingAuthorityEn

Rules for final values:
- Return only values visible in the image.
- Do not invent or infer missing values — use null.
- Keep Arabic in Arabic script exactly as seen.
- Keep English in the case shown (usually UPPERCASE).
- GivenNameTokensAr/GivenNameTokensEn must contain the ordered given-name tokens only.
- If there are more than three given names, keep all of them in the token arrays.
- Dates must be DD/MM/YYYY format. If uncertain, return null.
- Sex must be "M" or "F". If uncertain, return null.
- MRZ lines: return the full 44-character string including filler <'s.
""".strip()
