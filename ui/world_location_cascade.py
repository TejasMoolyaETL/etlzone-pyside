"""Wire Country → State → City combos from ``data/world_locations.json``."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QComboBox, QLabel

from core.world_locations_catalog import WorldLocationsIndex, load_world_locations_index
from ui.searchable_form_combo import (
    combo_resolved_item_data,
    reset_searchable_combo,
    sync_combo_index_from_display_text,
    wire_searchable_labeled_rows_combo,
)

_WIRE_KW = dict(select_first_on_fill=False)


def set_world_location_inline_error(country: QComboBox, message: str) -> None:
    """Show a short validation line under the location fields (no modal)."""
    lab = getattr(country, "_world_loc_inline_error", None)
    if lab is None or not isinstance(lab, QLabel):
        return
    text = (message or "").strip()
    lab.setText(text)
    lab.setVisible(bool(text))


def clear_world_location_inline_error(country: QComboBox) -> None:
    set_world_location_inline_error(country, "")


def _empty_state_city(state: QComboBox, city: QComboBox) -> None:
    state.blockSignals(True)
    city.blockSignals(True)
    wire_searchable_labeled_rows_combo(
        state, rows=[], search_field_label="State", **_WIRE_KW
    )
    wire_searchable_labeled_rows_combo(
        city, rows=[], search_field_label="City", **_WIRE_KW
    )
    state.blockSignals(False)
    city.blockSignals(False)


class _WorldLocParentGuard(QObject):
    """Prompt for Country / State order via inline label (no modal dialogs)."""

    def __init__(
        self,
        role: str,
        country: QComboBox,
        state: QComboBox,
        city: QComboBox,
    ) -> None:
        super().__init__(country)
        self._role = role
        self._country = country
        self._state = state
        self._city = city
        self._queued = False

    def _defer(self, fn) -> None:
        """Do not run feedback synchronously from ``eventFilter`` (focus glitches on Windows)."""
        if self._queued:
            return
        self._queued = True

        def _run() -> None:
            try:
                fn()
            except RuntimeError:
                pass
            finally:
                self._queued = False

        QTimer.singleShot(0, _run)

    def _warn_country_first(self) -> None:
        if combo_resolved_item_data(self._country):
            clear_world_location_inline_error(self._country)
            return
        set_world_location_inline_error(self._country, "Select country first.")
        QTimer.singleShot(0, self._focus_country)

    def _warn_select_state_first(self) -> None:
        cc = combo_resolved_item_data(self._country)
        sync_combo_index_from_display_text(self._state, emit_change=True)
        st = combo_resolved_item_data(self._state)
        if not cc:
            self._warn_country_first()
            return
        if st is not None and str(st).strip():
            clear_world_location_inline_error(self._country)
            return
        set_world_location_inline_error(self._country, "Select state first.")
        QTimer.singleShot(0, self._focus_state)

    def _focus_country(self) -> None:
        try:
            self._country.setFocus()
        except RuntimeError:
            pass

    def _focus_state(self) -> None:
        try:
            self._state.setFocus()
        except RuntimeError:
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: ARG002
        combo = self._state if self._role == "state" else self._city
        le = combo.lineEdit()
        if watched is not combo and (le is None or watched is not le):
            return False
        if event.type() not in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
            return False
        cc = combo_resolved_item_data(self._country)
        if self._role == "state":
            if not cc:
                self._defer(self._warn_country_first)
            return False
        if not cc:
            self._defer(self._warn_country_first)
            return False
        sync_combo_index_from_display_text(self._state, emit_change=True)
        st = combo_resolved_item_data(self._state)
        if st is None or not str(st).strip():
            self._defer(self._warn_select_state_first)
            return False
        clear_world_location_inline_error(self._country)
        return False


def _install_world_loc_guards(country: QComboBox, state: QComboBox, city: QComboBox) -> None:
    if getattr(country, "_world_loc_guards_installed", False):
        return
    st_guard = _WorldLocParentGuard("state", country, state, city)
    ci_guard = _WorldLocParentGuard("city", country, state, city)
    st_guard.setParent(country)
    ci_guard.setParent(country)
    for w in (state, state.lineEdit()):
        if w is not None:
            w.installEventFilter(st_guard)
    for w in (city, city.lineEdit()):
        if w is not None:
            w.installEventFilter(ci_guard)
    setattr(country, "_world_loc_state_guard", st_guard)
    setattr(country, "_world_loc_city_guard", ci_guard)
    setattr(country, "_world_loc_guards_installed", True)

    def _clear_inline_hint() -> None:
        clear_world_location_inline_error(country)

    for loc_combo in (state, city):
        setattr(loc_combo, "_world_loc_clear_inline_error", _clear_inline_hint)


def ensure_world_locations_cascade(
    country: QComboBox,
    state: QComboBox,
    city: QComboBox,
    *,
    inline_error_label: QLabel | None = None,
) -> bool:
    """Populate countries and wire dependent lists. Returns False if JSON is missing."""
    idx = load_world_locations_index()
    if idx is None:
        return False
    if inline_error_label is not None:
        setattr(country, "_world_loc_inline_error", inline_error_label)
    if getattr(country, "_world_loc_cascade_attached", False):
        setattr(country, "_world_loc_index", idx)
        return True

    def refill_states(_i: int = -1) -> None:
        clear_world_location_inline_error(country)
        cc = combo_resolved_item_data(country)
        if not cc:
            _empty_state_city(state, city)
            return
        wire_searchable_labeled_rows_combo(
            state,
            rows=idx.state_rows(str(cc)),
            search_field_label="State",
            **_WIRE_KW,
        )
        refill_cities()

    def refill_cities(_i: int = -1) -> None:
        clear_world_location_inline_error(country)
        cc = combo_resolved_item_data(country)
        st = combo_resolved_item_data(state)
        if not cc or st is None or str(st).strip() == "":
            city.blockSignals(True)
            wire_searchable_labeled_rows_combo(
                city, rows=[], search_field_label="City", **_WIRE_KW
            )
            city.blockSignals(False)
            return
        wire_searchable_labeled_rows_combo(
            city,
            rows=idx.city_rows(str(cc), str(st)),
            search_field_label="City",
            **_WIRE_KW,
        )

    wire_searchable_labeled_rows_combo(
        country,
        rows=idx.country_rows(),
        search_field_label="Country",
        **_WIRE_KW,
    )
    country.currentIndexChanged.connect(refill_states)
    state.currentIndexChanged.connect(refill_cities)
    setattr(country, "_world_loc_cascade_attached", True)
    setattr(country, "_world_loc_index", idx)
    reset_searchable_combo(country)
    _empty_state_city(state, city)
    _install_world_loc_guards(country, state, city)
    return True


def apply_world_location_selection(
    country: QComboBox,
    state: QComboBox,
    city: QComboBox,
    *,
    country_iso: str | None,
    state_code: str | None,
    city_geoname_id: str | None,
    index: WorldLocationsIndex | None = None,
) -> None:
    """Set the three combos from codes (best-effort). Requires cascade to be attached first."""
    from ui.searchable_form_combo import set_searchable_combo_by_user_data

    idx = index or getattr(country, "_world_loc_index", None)
    if idx is None:
        idx = load_world_locations_index()
    if idx is None:
        return

    wire_searchable_labeled_rows_combo(
        country,
        rows=idx.country_rows(),
        search_field_label="Country",
        **_WIRE_KW,
    )
    if country_iso:
        set_searchable_combo_by_user_data(country, str(country_iso).strip().upper())
    else:
        reset_searchable_combo(country)

    cc = combo_resolved_item_data(country)
    if not cc:
        _empty_state_city(state, city)
        clear_world_location_inline_error(country)
        return

    wire_searchable_labeled_rows_combo(
        state,
        rows=idx.state_rows(str(cc)),
        search_field_label="State",
        **_WIRE_KW,
    )
    if state_code:
        set_searchable_combo_by_user_data(state, str(state_code).strip())
    else:
        reset_searchable_combo(state)

    st = combo_resolved_item_data(state)
    if not st:
        city.blockSignals(True)
        wire_searchable_labeled_rows_combo(
            city, rows=[], search_field_label="City", **_WIRE_KW
        )
        city.blockSignals(False)
        clear_world_location_inline_error(country)
        return

    wire_searchable_labeled_rows_combo(
        city,
        rows=idx.city_rows(str(cc), str(st)),
        search_field_label="City",
        **_WIRE_KW,
    )
    if city_geoname_id:
        set_searchable_combo_by_user_data(city, str(city_geoname_id).strip())
    else:
        reset_searchable_combo(city)
    clear_world_location_inline_error(country)


def reset_world_locations_cascading(country: QComboBox, state: QComboBox, city: QComboBox) -> None:
    if not getattr(country, "_world_loc_cascade_attached", False):
        reset_searchable_combo(country)
        reset_searchable_combo(state)
        reset_searchable_combo(city)
        clear_world_location_inline_error(country)
        return
    idx = load_world_locations_index()
    if idx is None:
        reset_searchable_combo(country)
        reset_searchable_combo(state)
        reset_searchable_combo(city)
        clear_world_location_inline_error(country)
        return
    wire_searchable_labeled_rows_combo(
        country,
        rows=idx.country_rows(),
        search_field_label="Country",
        **_WIRE_KW,
    )
    reset_searchable_combo(country)
    _empty_state_city(state, city)
    clear_world_location_inline_error(country)
