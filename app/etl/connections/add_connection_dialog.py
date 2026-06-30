"""Modal dialog to add a new database connection."""



from __future__ import annotations



from collections.abc import Callable

from typing import Any



from PySide6.QtCore import QThread, Qt, Slot

from PySide6.QtWidgets import (

    QComboBox,

    QDialog,

    QFormLayout,

    QFrame,

    QHBoxLayout,

    QLabel,

    QLineEdit,

    QPushButton,

    QSizePolicy,

    QVBoxLayout,

    QWidget,

)



from app.etl.connections.connection_async import (

    CONNECTION_FEEDBACK_PENDING_STYLE,

    ConnectionApiWorker,

)

from app.user_management.users.user_create import INPUT_STYLE

from app.user_management.user_timepass.user_role_ui_helpers import _add_view_user_form_row

from ui.form_combobox_style import apply_form_combobox_field

from ui.form_page_styles import (

    FORM_ERROR_LABEL_STYLE,

    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,

    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,

    MODAL_FEEDBACK_SUCCESS_STYLE,

    MODAL_FIELD_HEIGHT_PX,

    placeholder_enter,

)





def _parse_optional_int(text: str) -> int | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def build_connection_payload(

    *,

    connection_name: str,

    db_type: str,

    host: str,

    port_text: str,

    database_name: str,

    username: str,

    password: str,

    fetch_size_text: str = "",

    chunk_size_text: str = "",

) -> dict[str, Any]:

    port_value: int | None

    try:

        port_value = int(port_text.strip()) if port_text.strip() else None

    except ValueError:

        port_value = None

    payload: dict[str, Any] = {

        "connectionName": connection_name.strip(),

        "dbType": db_type.strip(),

        "host": host.strip(),

        "port": port_value,

        "databaseName": database_name.strip(),

        "username": username.strip(),

        "password": password.strip(),

    }

    fetch_size = _parse_optional_int(fetch_size_text)

    chunk_size = _parse_optional_int(chunk_size_text)

    if fetch_size is not None:

        payload["fetchSize"] = fetch_size

    if chunk_size is not None:

        payload["chunkSize"] = chunk_size

    return payload





class AddConnectionDialog(QDialog):

    """Add connection — same modal chrome as Assign Reporting Manager."""



    def __init__(

        self,

        parent: QWidget | None = None,

        *,

        on_test: Callable[[dict[str, Any]], dict[str, Any]] | None = None,

        on_save: Callable[[dict[str, Any]], dict[str, Any]] | None = None,

    ) -> None:

        super().__init__(parent)

        self._on_test = on_test

        self._on_save = on_save

        self.success_message = "Connection saved."

        self._async_busy = False

        self._api_thread: QThread | None = None

        self._api_worker: ConnectionApiWorker | None = None

        self.setWindowTitle("Add Connection")

        self.setModal(True)

        self.setMinimumWidth(620)

        self.setStyleSheet("QDialog { background: #ffffff; }")



        layout = QVBoxLayout(self)

        layout.setContentsMargins(16, 16, 16, 16)

        layout.setSpacing(10)



        self.msg = QLabel()

        self.msg.setWordWrap(True)

        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)

        self.msg.setTextInteractionFlags(

            Qt.TextInteractionFlag.TextSelectableByMouse

            | Qt.TextInteractionFlag.TextSelectableByKeyboard

        )

        self.msg.setVisible(False)

        layout.addWidget(self.msg)



        form_opts = {

            "contents_margins": (0, 0, 0, 0),

            "h_spacing": 12,

            "v_spacing": 8,

            "label_align": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,

        }



        def _make_form() -> QFormLayout:

            f = QFormLayout()

            f.setContentsMargins(*form_opts["contents_margins"])

            f.setHorizontalSpacing(form_opts["h_spacing"])

            f.setVerticalSpacing(form_opts["v_spacing"])

            f.setLabelAlignment(form_opts["label_align"])

            return f



        fh = MODAL_FIELD_HEIGHT_PX

        form = _make_form()



        def _line_field(placeholder: str, *, default: str = "") -> QLineEdit:

            w = QLineEdit()

            if default:

                w.setText(default)

            w.setPlaceholderText(placeholder)

            w.setStyleSheet(INPUT_STYLE)

            w.setFixedHeight(fh)

            w.setMinimumWidth(360)

            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            return w



        self._name = _line_field(placeholder_enter("connection name"))

        _add_view_user_form_row(form, "Connection Name*", self._name)



        self._db_type = QComboBox()

        self._db_type.addItems(["ORACLE", "MYSQL", "POSTGRES"])

        apply_form_combobox_field(self._db_type, height_px=fh, min_width=360)

        _add_view_user_form_row(form, "Db Type*", self._db_type)



        self._host = _line_field(placeholder_enter("host"), default="localhost")

        _add_view_user_form_row(form, "Host*", self._host)



        self._port = _line_field(placeholder_enter("port"))

        _add_view_user_form_row(form, "Port", self._port)



        self._database = _line_field(placeholder_enter("database or service name"))

        _add_view_user_form_row(form, "Database / Service*", self._database)



        self._username = _line_field(placeholder_enter("username"))

        _add_view_user_form_row(form, "Username*", self._username)



        self._password = _line_field(placeholder_enter("password"))

        self._password.setEchoMode(QLineEdit.EchoMode.Password)

        _add_view_user_form_row(form, "Password*", self._password)



        self._fetch_size = _line_field(placeholder_enter("fetch size"), default="2000")

        _add_view_user_form_row(form, "Fetch Size", self._fetch_size)



        self._chunk_size = _line_field(placeholder_enter("chunk size"), default="2000")

        _add_view_user_form_row(form, "Chunk Size", self._chunk_size)



        self._form_fields: tuple[QWidget, ...] = (

            self._name,

            self._db_type,

            self._host,

            self._port,

            self._database,

            self._username,

            self._password,

            self._fetch_size,

            self._chunk_size,

        )



        layout.addLayout(form)



        sep = QFrame()

        sep.setFrameShape(QFrame.Shape.HLine)

        sep.setFrameShadow(QFrame.Shadow.Plain)

        sep.setFixedHeight(1)

        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")

        layout.addWidget(sep)



        self._test_btn = QPushButton("Test")

        self._test_btn.setFixedWidth(100)

        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._test_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)

        self._test_btn.clicked.connect(self._test_connection)



        self._save_btn = QPushButton("Save")

        self._save_btn.setFixedWidth(100)

        self._save_btn.setDefault(True)

        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)

        self._save_btn.clicked.connect(self._save_connection)



        self._cancel_btn = QPushButton("Cancel")

        self._cancel_btn.setFixedWidth(100)

        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)

        self._cancel_btn.clicked.connect(self.reject)



        btn_row = QWidget()

        btn_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        br = QHBoxLayout(btn_row)

        br.setContentsMargins(0, 0, 0, 0)

        br.setSpacing(12)

        br.setAlignment(Qt.AlignmentFlag.AlignLeft)

        br.addWidget(self._test_btn)

        br.addWidget(self._save_btn)

        br.addWidget(self._cancel_btn)

        br.addStretch(1)

        layout.addWidget(btn_row)



    def _api_thread_running(self) -> bool:

        return self._api_thread is not None and self._api_thread.isRunning()



    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]

        if self._api_thread_running():

            event.ignore()

            return

        super().closeEvent(event)



    def reject(self) -> None:

        if self._async_busy:

            return

        super().reject()



    def _payload(self) -> dict[str, Any]:

        return build_connection_payload(

            connection_name=self._name.text(),

            db_type=self._db_type.currentText(),

            host=self._host.text(),

            port_text=self._port.text(),

            database_name=self._database.text(),

            username=self._username.text(),

            password=self._password.text(),

            fetch_size_text=self._fetch_size.text(),

            chunk_size_text=self._chunk_size.text(),

        )



    def _clear_msg(self) -> None:

        self.msg.clear()

        self.msg.setVisible(False)

        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)



    def _show_err(self, text: str) -> None:

        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)

        self.msg.setText(text)

        self.msg.setVisible(bool(text))



    def _show_ok(self, text: str) -> None:

        self.msg.setStyleSheet(MODAL_FEEDBACK_SUCCESS_STYLE)

        self.msg.setText(text)

        self.msg.setVisible(bool(text))



    def _show_pending(self, text: str) -> None:

        self.msg.setStyleSheet(CONNECTION_FEEDBACK_PENDING_STYLE)

        self.msg.setText(text)

        self.msg.setVisible(True)



    def _set_async_busy(self, busy: bool) -> None:

        self._async_busy = busy

        self._test_btn.setEnabled(not busy)

        self._save_btn.setEnabled(not busy)

        self._cancel_btn.setEnabled(not busy)

        for field in self._form_fields:

            field.setEnabled(not busy)



    def _validate_name(self) -> bool:

        if not self._name.text().strip():

            self._show_err("Connection name is required.")

            return False

        return True



    def _start_async(

        self,

        *,

        payload: dict[str, Any],

        on_call: Callable[[dict[str, Any]], dict[str, Any]],

        pending_text: str,

        fail_prefix: str,

        finished_handler: Callable[[object], None],

    ) -> None:

        if self._async_busy:

            return

        self._set_async_busy(True)

        self._show_pending(pending_text)



        self._api_thread = QThread(self)

        self._api_worker = ConnectionApiWorker(payload, on_call, fail_prefix=fail_prefix)

        self._api_worker.moveToThread(self._api_thread)

        self._api_thread.started.connect(self._api_worker.run)

        self._api_worker.finished.connect(finished_handler)

        self._api_worker.finished.connect(self._api_thread.quit)

        self._api_thread.finished.connect(self._cleanup_api_thread)

        self._api_thread.start()



    def _test_connection(self) -> None:

        self._clear_msg()

        if self._async_busy:

            return

        if not self._on_test:

            return

        if not self._validate_name():

            return

        self._start_async(

            payload=self._payload(),

            on_call=self._on_test,

            pending_text="Testing…",

            fail_prefix="Test failed",

            finished_handler=self._on_test_finished,

        )



    @Slot(object)

    def _on_test_finished(self, result: object) -> None:

        self._set_async_busy(False)

        if not isinstance(result, dict):

            self._show_err("Test failed.")

            return

        if result.get("success"):

            self._show_ok(str(result.get("message") or "Connection successful."))

        else:

            self._show_err(str(result.get("message") or "Test failed."))



    def _save_connection(self) -> None:

        self._clear_msg()

        if self._async_busy:

            return

        if not self._on_save:

            return

        if not self._validate_name():

            return

        self._start_async(

            payload=self._payload(),

            on_call=self._on_save,

            pending_text="Saving…",

            fail_prefix="Save failed",

            finished_handler=self._on_save_finished,

        )



    @Slot(object)

    def _on_save_finished(self, result: object) -> None:

        self._set_async_busy(False)

        if not isinstance(result, dict):

            self._show_err("Save failed.")

            return

        if result.get("success"):

            self.success_message = str(result.get("message") or "Connection saved.")

            self.accept()

        else:

            self._show_err(str(result.get("message") or "Save failed."))



    def _cleanup_api_thread(self) -> None:

        if self._api_worker is not None:

            self._api_worker.deleteLater()

            self._api_worker = None

        if self._api_thread is not None:

            self._api_thread.deleteLater()

            self._api_thread = None


