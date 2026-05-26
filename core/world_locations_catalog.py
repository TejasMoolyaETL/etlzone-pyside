"""Hierarchical world locations for Country → State → City (``data/world_locations.json``).

Build with::

    python scripts/build_world_cities_json.py

That writes ``data/world_locations.json`` (nested tree). Dropdowns show **country / state / city names**; create/update
API payloads use those same display strings (e.g. ``India``, ``Maharashtra``,
``Mumbai``). Internal keys (ISO2, admin1 ``stateCode``, GeoNames city id) stay
in combo ``userData`` for cascading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORLD_LOCATIONS_PATH = _PROJECT_ROOT / "data" / "world_locations.json"

_index_cache: tuple[float, "WorldLocationsIndex"] | None = None


def world_locations_json_path() -> Path:
    return DEFAULT_WORLD_LOCATIONS_PATH


def world_locations_available(path: Path | None = None) -> bool:
    p = path or DEFAULT_WORLD_LOCATIONS_PATH
    return p.is_file()


def _norm_name(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _strip_master_key_value_display(s: str) -> str:
    t = (s or "").strip()
    if "|" in t:
        return t.split("|", 1)[1].strip()
    return t


def _master_display_hint(val: Any) -> str:
    if isinstance(val, dict):
        for k in ("keyValue", "key_value", "name", "label", "displayName"):
            t = str(val.get(k) or "").strip()
            if t:
                return t
    return str(val or "").strip()


class WorldLocationsIndex:
    """In-memory index built from ``world_locations.json``."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self._countries: list[dict[str, Any]] = []
        raw = doc.get("countries")
        if isinstance(raw, list):
            for c in raw:
                if isinstance(c, dict) and str(c.get("code", "")).strip():
                    self._countries.append(c)
        self._countries.sort(key=lambda x: str(x.get("name") or x.get("code") or "").lower())

    def country_rows(self) -> list[tuple[str, str]]:
        """Combo rows: visible **country name** (e.g. India), ``userData`` = ISO2 for cascading."""
        out: list[tuple[str, str]] = []
        for c in self._countries:
            code = str(c.get("code") or "").strip().upper()
            name = str(c.get("name") or code).strip()
            if not code:
                continue
            out.append((name, code))
        return out

    def _country_entry(self, iso2: str) -> dict[str, Any] | None:
        u = (iso2 or "").strip().upper()
        for c in self._countries:
            if str(c.get("code") or "").strip().upper() == u:
                return c
        return None

    def state_rows(self, country_iso2: str) -> list[tuple[str, str]]:
        c = self._country_entry(country_iso2)
        if c is None:
            return []
        states = c.get("states")
        if not isinstance(states, list):
            return []
        acc: list[tuple[str, str, str]] = []
        for st in states:
            if not isinstance(st, dict):
                continue
            sc = str(st.get("code") or "").strip()
            sn = (str(st.get("name") or sc).strip() or sc or "—").strip()
            acc.append((_norm_name(sn), sn, sc))
        acc.sort(key=lambda t: t[0])
        return [(t[1], t[2]) for t in acc]

    def city_rows(self, country_iso2: str, state_code: str) -> list[tuple[str, str]]:
        c = self._country_entry(country_iso2)
        if c is None:
            return []
        states = c.get("states")
        if not isinstance(states, list):
            return []
        want = (state_code or "").strip()
        for st in states:
            if not isinstance(st, dict):
                continue
            sc = str(st.get("code") or "").strip()
            if sc != want:
                continue
            cities = st.get("cities")
            if not isinstance(cities, list):
                return []
            triples: list[tuple[str, str, str]] = []
            for row in cities:
                if not isinstance(row, dict):
                    continue
                gid = str(row.get("code") or "").strip()
                nm = str(row.get("name") or "").strip()
                if not gid or not nm:
                    continue
                triples.append((_norm_name(nm), nm, gid))
            triples.sort(key=lambda t: t[0])
            return [(t[1], t[2]) for t in triples]
        return []

    def display_names_for_api(
        self, country_iso2: str, state_code: str, city_geoname: str
    ) -> tuple[str, str, str]:
        """Resolve internal keys to API-facing display strings (e.g. India / Maharashtra / Mumbai)."""
        cc = (country_iso2 or "").strip().upper()
        sc = (state_code or "").strip()
        gid = str(city_geoname or "").strip()
        c_ent = self._country_entry(cc)
        cname = str(c_ent.get("name") or cc).strip() if c_ent else cc
        sname = sc
        ciname = gid
        if not c_ent:
            return cname, sname, ciname
        states = c_ent.get("states")
        if not isinstance(states, list):
            return cname, sname, ciname
        for st in states:
            if not isinstance(st, dict):
                continue
            if str(st.get("code") or "").strip() != sc:
                continue
            sname = str(st.get("name") or sc).strip() or sc
            cities = st.get("cities")
            if isinstance(cities, list):
                for row in cities:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("code") or "").strip() != gid:
                        continue
                    ciname = str(row.get("name") or gid).strip() or gid
                    return cname, sname, ciname
            return cname, sname, ciname
        return cname, sname, ciname

    def resolve_from_labels(
        self, country_labelish: str, state_labelish: str, city_labelish: str
    ) -> tuple[str | None, str | None, str | None]:
        """Map display strings (e.g. master ``keyValue``) to ``(iso2, stateCode, cityGeonameId)``."""
        raw_c = _strip_master_key_value_display(country_labelish)
        raw_s = _strip_master_key_value_display(state_labelish)
        raw_t = _strip_master_key_value_display(city_labelish)
        cn = _norm_name(raw_c)
        sn = _norm_name(raw_s)
        tin = _norm_name(raw_t)

        cc_out: str | None = None
        if len(raw_c) == 2 and raw_c.isalpha():
            cc_out = raw_c.upper()
        if not cc_out and cn:
            for c in self._countries:
                ccode = str(c.get("code") or "").strip().upper()
                cnm = _norm_name(str(c.get("name") or ""))
                if cnm == cn:
                    cc_out = ccode
                    break
        if not cc_out:
            return None, None, None

        st_out: str | None = None
        c_ent = self._country_entry(cc_out)
        if c_ent is None:
            return cc_out, None, None
        states = c_ent.get("states")
        if isinstance(states, list):
            rs = raw_s.strip().upper()
            if len(rs) > 2 and "-" in rs:
                for st in states:
                    if not isinstance(st, dict):
                        continue
                    s_cd = str(st.get("code") or "").strip().upper()
                    if s_cd == rs:
                        st_out = str(st.get("code") or "").strip()
                        break
            if not st_out and sn:
                for st in states:
                    if not isinstance(st, dict):
                        continue
                    s_nm = _norm_name(str(st.get("name") or ""))
                    s_cd = str(st.get("code") or "").strip()
                    if s_nm == sn or _norm_name(s_cd) == sn:
                        st_out = s_cd
                        break

        city_id: str | None = None
        if st_out and tin:
            for lab, gid in self.city_rows(cc_out, st_out):
                if _norm_name(lab) == tin:
                    city_id = gid
                    break
        if not city_id and raw_t.strip().isdigit():
            city_id = raw_t.strip()

        return cc_out, st_out, city_id


def _looks_like_iso_admin1_state_code(s: str) -> bool:
    """True for values such as ``IN-MH`` or ``US-CA`` (not plain ``Maharashtra``)."""
    t = (s or "").strip().upper()
    return len(t) > 3 and t[2] == "-" and t[:2].isalpha() and t[3:].replace(".", "").isalnum()


def geo_triple_from_company_record(
    record: dict[str, Any],
    *,
    index: WorldLocationsIndex | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Best-effort ``(countryIso2, stateCode, cityGeonameId_str)`` from a company API dict."""
    if not isinstance(record, dict):
        return None, None, None

    c_raw = record.get("country")
    s_raw = record.get("state")
    city_raw = record.get("city")

    cc: str | None = None
    if isinstance(c_raw, str) and len(c_raw.strip()) == 2 and c_raw.strip().isalpha():
        cc = c_raw.strip().upper()

    st: str | None = None
    if isinstance(s_raw, str) and s_raw.strip():
        raw_s = s_raw.strip()
        if _looks_like_iso_admin1_state_code(raw_s):
            st = raw_s.strip().upper()

    city_id: str | None = None
    if isinstance(city_raw, (int, float)) and city_raw == int(city_raw) and int(city_raw) > 0:
        city_id = str(int(city_raw))
    elif isinstance(city_raw, str) and city_raw.strip().isdigit():
        city_id = city_raw.strip()

    if cc and st and city_id:
        return cc, st, city_id

    if index is None:
        return cc, st, city_id

    r_cc, r_st, r_ci = index.resolve_from_labels(
        _master_display_hint(c_raw),
        _master_display_hint(s_raw),
        _master_display_hint(city_raw),
    )
    return cc or r_cc, r_st or st, city_id or r_ci


def load_world_locations_index(path: Path | None = None) -> WorldLocationsIndex | None:
    global _index_cache
    p = path or DEFAULT_WORLD_LOCATIONS_PATH
    if not p.is_file():
        _index_cache = None
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    if _index_cache is not None and _index_cache[0] == mtime:
        return _index_cache[1]
    try:
        with p.open(encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        _index_cache = None
        return None
    if not isinstance(doc, dict):
        _index_cache = None
        return None
    idx = WorldLocationsIndex(doc)
    _index_cache = (mtime, idx)
    return idx
