#!/usr/bin/env python3
"""Download GeoNames data and write ``data/world_locations.json``.

Hierarchical ``world_locations.json`` (Country → State → City). Each city entry
includes ``country`` and ``state`` as **display names** (e.g. India, Maharashtra)
alongside ``code`` (GeoNames id) and ``name`` (city) so rows match API-style
strings::

    { "code": "1275339", "name": "Mumbai", "country": "India", "state": "Maharashtra" }

``stateCode`` is normally GeoNames admin1 with the dot replaced by a hyphen
(``US.CA`` → ``US-CA``). India is special: GeoNames uses numeric adm1
(``IN.02``) but we emit ISO 3166-2 style codes (``IN-AP`` for Andhra Pradesh).

Requires network access. Run from repo root::

    python scripts/build_world_cities_json.py

Sources (see https://www.geonames.org/export/ ):

- ``cities15000.zip`` — populated places with population ≥ 15,000 or capitals
- ``admin1CodesASCII.txt`` — region names for ``country + admin1`` codes
- ``countryInfo.txt`` — ISO country code → country name
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_LOCATIONS_PATH = ROOT / "data" / "world_locations.json"

CITIES_ZIP_URL = "https://download.geonames.org/export/dump/cities15000.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
COUNTRY_URL = "https://download.geonames.org/export/dump/countryInfo.txt"


def _norm_admin_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


# GeoNames India uses numeric admin1 ids (IN.02, …); ISO 3166-2 uses letter codes (IN-AP, …).
_IN_STATE_NAME_TO_ISO_SUFFIX: dict[str, str] = {
    _norm_admin_name(k): v
    for k, v in (
        ("Andaman and Nicobar", "AN"),
        ("Andhra Pradesh", "AP"),
        ("Arunachal Pradesh", "AR"),
        ("Assam", "AS"),
        ("Bihar", "BR"),
        ("Chandigarh", "CH"),
        ("Chhattisgarh", "CT"),
        ("Dadra and Nagar Haveli and Daman and Diu", "DH"),
        ("Delhi", "DL"),
        ("Goa", "GA"),
        ("Gujarat", "GJ"),
        ("Haryana", "HR"),
        ("Himachal Pradesh", "HP"),
        ("Jammu and Kashmir", "JK"),
        ("Jharkhand", "JH"),
        ("Karnataka", "KA"),
        ("Kerala", "KL"),
        ("Ladakh", "LA"),
        ("Lakshadweep", "LD"),
        ("Madhya Pradesh", "MP"),
        ("Maharashtra", "MH"),
        ("Manipur", "MN"),
        ("Meghalaya", "ML"),
        ("Mizoram", "MZ"),
        ("Nagaland", "NL"),
        ("Odisha", "OR"),
        ("Puducherry", "PY"),
        ("Punjab", "PB"),
        ("Rajasthan", "RJ"),
        ("Sikkim", "SK"),
        ("Tamil Nadu", "TN"),
        ("Telangana", "TG"),
        ("Tripura", "TR"),
        ("Uttar Pradesh", "UP"),
        ("Uttarakhand", "UT"),
        ("West Bengal", "WB"),
    )
}
_IN_STATE_NAME_TO_ISO_SUFFIX["orissa"] = "OR"


def _iso3166_2_state_code(country_iso: str, adm_key: str, state_name: str) -> str:
    """``CC.ADM`` → ``CC-ADM``; India maps GeoNames state names to ISO letter suffixes (e.g. IN-AP)."""
    if not adm_key:
        return ""
    if country_iso == "IN":
        key = _norm_admin_name(state_name)
        suf = _IN_STATE_NAME_TO_ISO_SUFFIX.get(key)
        if suf:
            return f"IN-{suf}"
    return adm_key.replace(".", "-", 1)


def _fetch_bytes(url: str) -> bytes:
    req = urlopen(url, timeout=120)  # noqa: S310 — intentional GeoNames download
    try:
        return req.read()
    finally:
        req.close()


def _load_country_names(raw: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        iso = parts[0].strip().upper()
        name = parts[4].strip()
        if iso and name:
            out[iso] = name
    return out


def _load_admin1_names(raw: bytes) -> dict[str, str]:
    """Map ``CC.ADM1`` (e.g. ``IN.16``) -> region display name."""
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0].strip()
        name = parts[1].strip()
        if code and name:
            out[code] = name
    return out


def main() -> int:
    OUT_LOCATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading countryInfo.txt …", flush=True)
    countries = _load_country_names(_fetch_bytes(COUNTRY_URL))
    print(f"  {len(countries)} countries", flush=True)

    print("Downloading admin1CodesASCII.txt …", flush=True)
    admin1 = _load_admin1_names(_fetch_bytes(ADMIN1_URL))
    print(f"  {len(admin1)} admin1 rows", flush=True)

    print("Downloading cities15000.zip …", flush=True)
    zdata = _fetch_bytes(CITIES_ZIP_URL)
    cities: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        if not names:
            print("No .txt inside zip", file=sys.stderr)
            return 1
        txt = zf.read(names[0]).decode("utf-8", errors="replace")

    for line in txt.splitlines():
        if not line:
            continue
        p = line.split("\t")
        if len(p) < 11:
            continue
        geonameid = p[0].strip()
        asciiname = (p[2] or p[1]).strip()
        country_code = p[8].strip().upper()
        admin1_code = p[10].strip()
        if not geonameid or not asciiname or not country_code:
            continue
        country_name = countries.get(country_code, country_code)
        adm_key = f"{country_code}.{admin1_code}" if admin1_code else ""
        state_name = admin1.get(adm_key, admin1_code) if admin1_code else ""
        state_code = _iso3166_2_state_code(country_code, adm_key, state_name)
        row_out: dict[str, str] = {
            "code": geonameid,
            "name": asciiname,
            "country": country_name,
            "countryCode": country_code,
            "state": state_name,
            "stateCode": state_code,
        }
        cities.append(row_out)

    print(f"Parsed {len(cities)} cities from GeoNames", flush=True)

    # Hierarchical tree for cascading Country → State → City dropdowns.
    by_country: dict[str, dict[str, object]] = {}
    for r in cities:
        cc = str(r.get("countryCode") or "").strip().upper()
        if not cc:
            continue
        cname = str(r.get("country") or cc).strip()
        scode = str(r.get("stateCode") or "").strip()
        sname = str(r.get("state") or scode or "—").strip() or "—"
        cid = str(r.get("code") or "").strip()
        cnm = str(r.get("name") or "").strip()
        if not cid or not cnm:
            continue
        if cc not in by_country:
            by_country[cc] = {"code": cc, "name": cname, "_states": {}}
        entry = by_country[cc]
        states_map: dict[str, dict[str, object]] = entry["_states"]  # type: ignore[assignment]
        sk = scode if scode else "__"
        if sk not in states_map:
            states_map[sk] = {"code": scode, "name": sname, "_cities": {}}
        st_entry = states_map[sk]
        cities_map: dict[str, str] = st_entry["_cities"]  # type: ignore[assignment]
        cities_map[cid] = cnm

    countries_out: list[dict[str, object]] = []
    for cc in sorted(by_country.keys()):
        ent = by_country[cc]
        states_map: dict[str, dict[str, object]] = ent.pop("_states")  # type: ignore[misc]
        states_list: list[dict[str, object]] = []
        for sk in sorted(states_map.keys(), key=lambda k: (states_map[k]["name"] or "").lower()):  # type: ignore[index]
            st = states_map[sk]
            cmap: dict[str, str] = st.pop("_cities")  # type: ignore[misc]
            c_country = str(ent.get("name") or cc)
            c_state = str(st.get("name") or sk)
            city_rows = [
                {
                    "code": gid,
                    "name": nm,
                    "country": c_country,
                    "state": c_state,
                }
                for gid, nm in sorted(cmap.items(), key=lambda t: t[1].lower())
            ]
            states_list.append(
                {
                    "code": str(st.get("code") or ""),
                    "name": str(st.get("name") or ""),
                    "cities": city_rows,
                }
            )
        countries_out.append(
            {
                "code": str(ent.get("code") or cc),
                "name": str(ent.get("name") or cc),
                "states": states_list,
            }
        )

    locations_doc = {
        "version": 2,
        "source": "GeoNames cities15000 + admin1CodesASCII + countryInfo",
        "countries": countries_out,
    }
    with OUT_LOCATIONS_PATH.open("w", encoding="utf-8") as f:
        json.dump(locations_doc, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(countries_out)} countries to {OUT_LOCATIONS_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
