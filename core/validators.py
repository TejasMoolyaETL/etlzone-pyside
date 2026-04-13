"""Shared country codes, mobile validation, and helpers for profile/user forms."""

from __future__ import annotations

import re

# Country codes for mobile (code, country name) - ordered by common use
COUNTRY_CODES = (
    ("+91", "India"),
    ("+1", "US/Canada"),
    ("+44", "UK"),
    ("+971", "UAE"),
    ("+966", "Saudi Arabia"),
    ("+61", "Australia"),
    ("+81", "Japan"),
    ("+86", "China"),
    ("+49", "Germany"),
    ("+33", "France"),
    ("+39", "Italy"),
    ("+34", "Spain"),
    ("+31", "Netherlands"),
    ("+32", "Belgium"),
    ("+41", "Switzerland"),
    ("+43", "Austria"),
    ("+46", "Sweden"),
    ("+47", "Norway"),
    ("+48", "Poland"),
    ("+55", "Brazil"),
    ("+52", "Mexico"),
    ("+54", "Argentina"),
    ("+57", "Colombia"),
    ("+51", "Peru"),
    ("+56", "Chile"),
    ("+62", "Indonesia"),
    ("+63", "Philippines"),
    ("+65", "Singapore"),
    ("+60", "Malaysia"),
    ("+66", "Thailand"),
    ("+84", "Vietnam"),
    ("+82", "South Korea"),
    ("+7", "Russia"),
    ("+90", "Turkey"),
    ("+27", "South Africa"),
    ("+234", "Nigeria"),
    ("+254", "Kenya"),
    ("+20", "Egypt"),
    ("+92", "Pakistan"),
    ("+880", "Bangladesh"),
    ("+94", "Sri Lanka"),
    ("+977", "Nepal"),
)

# Mobile validation by country code: (min_len, max_len, optional_regex_pattern)
# Regex validates national number format (digits only, no country code)
MOBILE_VALIDATION: dict[str, tuple[int, int, str | None]] = {
    "+91": (10, 10, r"^[6-9]\d{9}$"),  # India: 10 digits, starts 6-9
    "+1": (10, 10, r"^\d{10}$"),  # US/Canada: 10 digits
    "+44": (10, 11, None),  # UK: 10-11 digits
    "+971": (9, 9, r"^5[0-9]\d{7}$"),  # UAE: 9 digits, starts 50-59
    "+966": (9, 9, r"^5[0-9]\d{7}$"),  # Saudi: 9 digits, starts 5x
    "+61": (9, 9, r"^4\d{8}$"),  # Australia: 9 digits, starts 4
    "+81": (10, 10, r"^[789]\d{9}$"),  # Japan: 10 digits, starts 7-9
    "+86": (11, 11, r"^1[3-9]\d{9}$"),  # China: 11 digits, starts 13-19
    "+49": (10, 11, None),  # Germany: 10-11 digits
    "+33": (9, 9, r"^[67]\d{8}$"),  # France: 9 digits, starts 6 or 7
    "+39": (9, 10, None),  # Italy: 9-10 digits
    "+34": (9, 9, r"^[67]\d{8}$"),  # Spain: 9 digits, starts 6 or 7
    "+31": (9, 9, r"^6\d{8}$"),  # Netherlands: 9 digits, starts 6
    "+32": (9, 9, None),  # Belgium: 9 digits
    "+41": (9, 9, None),  # Switzerland: 9 digits
    "+43": (10, 13, None),  # Austria: variable
    "+46": (9, 9, None),  # Sweden: 9 digits
    "+47": (8, 8, None),  # Norway: 8 digits
    "+48": (9, 9, r"^[5-9]\d{8}$"),  # Poland: 9 digits, starts 5-9
    "+55": (10, 11, None),  # Brazil: 10-11 digits
    "+52": (10, 10, None),  # Mexico: 10 digits
    "+54": (10, 10, None),  # Argentina: 10 digits
    "+57": (10, 10, r"^3[0-9]\d{8}$"),  # Colombia: 10 digits, starts 3x
    "+51": (9, 9, r"^9\d{8}$"),  # Peru: 9 digits, starts 9
    "+56": (9, 9, r"^9\d{8}$"),  # Chile: 9 digits, starts 9
    "+62": (9, 12, r"^8\d{8,11}$"),  # Indonesia: 9-12, starts 8
    "+63": (10, 10, r"^9\d{9}$"),  # Philippines: 10 digits, starts 9
    "+65": (8, 8, r"^[89]\d{7}$"),  # Singapore: 8 digits, starts 8 or 9
    "+60": (9, 10, None),  # Malaysia: 9-10 digits
    "+66": (9, 9, r"^[689]\d{8}$"),  # Thailand: 9 digits, starts 6,8,9
    "+84": (9, 10, None),  # Vietnam: 9-10 digits
    "+82": (9, 10, None),  # South Korea: 9-10 digits
    "+7": (10, 10, r"^9\d{9}$"),  # Russia: 10 digits, starts 9
    "+90": (10, 10, r"^5[0-9]\d{8}$"),  # Turkey: 10 digits, starts 5x
    "+27": (9, 9, r"^[6-8]\d{8}$"),  # South Africa: 9 digits, starts 6-8
    "+234": (10, 11, r"^[789]\d{9,10}$"),  # Nigeria: 10-11, starts 7-9
    "+254": (9, 9, r"^[17]\d{8}$"),  # Kenya: 9 digits, starts 1 or 7
    "+20": (10, 10, None),  # Egypt: 10 digits
    "+92": (10, 10, r"^3[0-9]\d{8}$"),  # Pakistan: 10 digits, starts 3x
    "+880": (10, 10, r"^1[3-9]\d{8}$"),  # Bangladesh: 10 digits, starts 13-19
    "+94": (9, 9, None),  # Sri Lanka: 9 digits
    "+977": (10, 10, r"^9[78]\d{8}$"),  # Nepal: 10 digits, starts 97 or 98
}


def validate_mobile(country_code: str, number: str) -> tuple[bool, str]:
    """Validate mobile number for given country code. Returns (is_valid, error_message)."""
    if not number:
        return True, ""
    if not number.isdigit():
        return False, "Mobile number must contain only digits."
    rules = MOBILE_VALIDATION.get(country_code)
    if rules:
        min_len, max_len, pattern = rules
        if len(number) < min_len:
            return False, f"Mobile number for {country_code} must be at least {min_len} digits."
        if len(number) > max_len:
            return False, f"Mobile number for {country_code} must be at most {max_len} digits."
        if pattern and not re.match(pattern, number):
            return False, f"Invalid mobile number format for {country_code}."
    else:
        if len(number) < 6:
            return False, "Mobile number must be at least 6 digits."
        if len(number) > 15:
            return False, "Mobile number must be at most 15 digits."
    return True, ""


def parse_mobile(value: str | None) -> tuple[str, str]:
    """Parse mobile value into (country_code, number). Returns (+91, "") as default."""
    if not value or not str(value).strip():
        return ("+91", "")
    s = str(value).strip().replace(" ", "").replace("-", "")
    if s.startswith("+"):
        sorted_codes = sorted(COUNTRY_CODES, key=lambda x: -len(x[0]))
        for code, _ in sorted_codes:
            if s == code or (len(s) > len(code) and s.startswith(code)):
                num = s[len(code) :]
                return (code, num)
    return ("+91", s.lstrip("0") or "")
