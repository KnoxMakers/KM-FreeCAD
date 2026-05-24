# -*- coding: utf-8 -*-
"""
KM-FreeCAD StartPage: Displays an interactive class browser on startup.

Shows every class folder under ~/Documents/FreeCAD/Classes, with each lesson
sub-folder and its files rendered as clickable thumbnail cards.

Clicking a .FCStd card opens the document in FreeCAD.
Clicking any other file opens it with the OS default application.

Backup files (.FCBak) are intentionally hidden.
"""

import os
import zipfile

import FreeCAD
from PySide import QtCore, QtGui, QtWidgets

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLASSES_DIR = os.path.join(os.path.expanduser("~"), "Documents", "FreeCAD", "Classes")

# Extensions that are shown as cards (backups are excluded)
_SHOW_EXT = {".fcstd", ".svg", ".png", ".jpg", ".jpeg", ".step", ".stp", ".dxf", ".pdf"}

# Extensions that should be opened inside FreeCAD rather than the OS viewer
_FREECAD_EXT = {".fcstd", ".svg", ".step", ".stp", ".dxf"}


_MODULE_LABELS = {
    "FreeCAD":   "Image formats (FreeCAD)",
    "importSVG": "SVG as geometry (importSVG)",
}

# Card and thumbnail dimensions
_THUMB_W   = 150
_THUMB_H   = 120
_CARD_W    = 170

# Addon directory (used to locate icon assets)
_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


def _module_label(mod):
    """Return a human-readable label for a FreeCAD importer module name."""
    base = mod[:-3] if mod.endswith("Gui") else mod
    return _MODULE_LABELS.get(base, base)


def _resolve_module(filepath):
    """Return the importer module name for *filepath*, or None if cancelled.

    Shows the SelectModule dialog when multiple importers are registered.
    Does NOT load the file — call _load_in_freecad() afterwards.
    """
    ext = os.path.splitext(filepath)[1].lstrip(".").lower()

    try:
        raw_modules = FreeCAD.getImportType(ext)
    except Exception:
        raw_modules = []

    # Deduplicate: drop "Gui" variants when the base module already appears.
    seen_bases = set()
    modules = []
    for mod in raw_modules:
        base = mod[:-3] if mod.endswith("Gui") else mod
        if base not in seen_bases:
            seen_bases.add(base)
            modules.append(mod)
    # getImportType returns importSVG before FreeCAD, which is the reverse of
    # FreeCAD's own SelectModule dialog. Flip to match.
    modules.reverse()

    if not modules:
        FreeCAD.Console.PrintWarning(f"KM-FreeCAD: No importer registered for .{ext}\n")
        return None

    if len(modules) == 1:
        return modules[0]

    # ---- Python replica of FreeCAD's C++ SelectModule dialog ----
    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle("Select Module")
    dlg.setWindowFlags(
        dlg.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
    )

    grid = QtWidgets.QGridLayout(dlg)
    grid.setSpacing(6)
    grid.setContentsMargins(9, 9, 9, 9)

    group_box = QtWidgets.QGroupBox(f"Open {ext} as")
    grid.addWidget(group_box, 0, 0)
    grid_inner = QtWidgets.QGridLayout(group_box)
    grid_inner.setSpacing(6)
    grid_inner.setContentsMargins(9, 9, 9, 9)

    btn_group = QtWidgets.QButtonGroup(dlg)
    for i, mod in enumerate(modules):
        rb = QtWidgets.QRadioButton(_module_label(mod))
        rb.setObjectName(mod)
        grid_inner.addWidget(rb, i, 0)
        btn_group.addButton(rb, i)

    grid.addItem(
        QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        ),
        1, 0,
    )

    btn_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Open | QtWidgets.QDialogButtonBox.Cancel
    )
    open_btn = btn_box.button(QtWidgets.QDialogButtonBox.Open)
    open_btn.setEnabled(False)
    grid.addWidget(btn_box, 2, 0)

    btn_box.accepted.connect(dlg.accept)
    btn_box.rejected.connect(dlg.reject)

    def _on_radio_toggled(checked, _open_btn=open_btn):
        if checked:
            _open_btn.setEnabled(True)

    for rb in [grid_inner.itemAt(i).widget() for i in range(grid_inner.count())]:
        if isinstance(rb, QtWidgets.QRadioButton):
            rb.toggled.connect(_on_radio_toggled)

    if dlg.exec_() != QtWidgets.QDialog.Accepted:
        return None

    checked_btn = btn_group.checkedButton()
    return checked_btn.objectName() if checked_btn else None


def _load_in_freecad(filepath, module):
    """Load *filepath* using *module* and run Fit All for SVG files."""
    ext = os.path.splitext(filepath)[1].lstrip(".").lower()
    try:
        FreeCAD.loadFile(filepath, "", module)
        _add_recent_file(filepath)
        if ext == "svg":
            try:
                import FreeCADGui
                FreeCADGui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            f"KM-FreeCAD: Could not open '{os.path.basename(filepath)}' "
            f"with {module}: {exc}\n"
        )


def _add_recent_file(filepath):
    """Add *filepath* to FreeCAD's recently-opened files list."""
    try:
        import FreeCADGui
        FreeCADGui.addRecentFile(filepath)
    except Exception:
        pass


def _is_dark_theme():
    """Return True when FreeCAD is running a dark UI theme.

    Checks in order of reliability:
    1. FreeCAD's stored stylesheet preference (the name contains 'dark').
    2. The main window's own widget palette (FreeCAD themes via widget-level
       stylesheets, so the app-level palette is often wrong).
    3. Application palette fallback.
    """
    # 1. FreeCAD preference — most reliable
    try:
        theme = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/MainWindow"
        ).GetString("Theme", "")
        if theme:
            return "dark" in theme.lower()
    except Exception:
        pass

    # 2. Main window widget palette
    try:
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        bg = mw.palette().color(mw.backgroundRole())
        return bg.lightness() < 128
    except Exception:
        pass

    # 3. Application palette fallback
    pal = QtWidgets.QApplication.palette()
    return pal.color(QtGui.QPalette.Window).lightness() < 128


def _palette_hex(role):
    """Return the current palette colour for *role* as a '#rrggbb' string."""
    return QtWidgets.QApplication.palette().color(role).name()


def _get_theme_colors():
    """Return a dict of all theme-aware UI colours, resolved in a single call.

    Call once at the start of each build function instead of calling
    _is_dark_theme() or _palette_hex() individually throughout.

    Keys: accent, card_bg, card_border, thumb_bg, thumb_border,
          text, badge, hdr_bg, hdr_title, hdr_path, hdr_btn_fg
    """
    if _is_dark_theme():
        return dict(
            accent       = "#e7e7e7",
            card_bg      = "#2d2d2d",
            card_border  = "#4a4a4a",
            thumb_bg     = "#1e1e1e",
            thumb_border = "#4a4a4a",
            text         = "#dddddd",
            badge        = "#888888",
            hdr_bg       = "#2d2d2d",
            hdr_title    = "#ffffff",
            hdr_path     = "#aaaaaa",
            hdr_btn_fg   = "#ffffff",
        )
    return dict(
        accent       = "#000000",
        card_bg      = _palette_hex(QtGui.QPalette.Base),
        card_border  = _palette_hex(QtGui.QPalette.Mid),
        thumb_bg     = _palette_hex(QtGui.QPalette.AlternateBase),
        thumb_border = _palette_hex(QtGui.QPalette.Mid),
        text         = _palette_hex(QtGui.QPalette.Text),
        badge        = _palette_hex(QtGui.QPalette.Dark),
        hdr_bg       = "#e8e8e8",
        hdr_title    = "#1e1e1e",
        hdr_path     = "#555555",
        hdr_btn_fg   = "#1e1e1e",
    )


# ---------------------------------------------------------------------------
# Thumbnail extraction
# ---------------------------------------------------------------------------

def _thumbnail_pixmap(filepath):
    """Return a scaled QPixmap for *filepath*, or None on failure."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".fcstd":
        try:
            with zipfile.ZipFile(filepath, "r") as z:
                for name in z.namelist():
                    if name.lower().startswith("thumbnails/") and name.lower().endswith(".png"):
                        data = z.read(name)
                        pix = QtGui.QPixmap()
                        pix.loadFromData(data)
                        if not pix.isNull():
                            return pix.scaled(
                                _THUMB_W, _THUMB_H,
                                QtCore.Qt.KeepAspectRatio,
                                QtCore.Qt.SmoothTransformation,
                            )
        except Exception:
            pass

    elif ext in (".svg", ".png", ".jpg", ".jpeg", ".bmp"):
        pix = QtGui.QPixmap(filepath)
        if not pix.isNull():
            return pix.scaled(
                _THUMB_W, _THUMB_H,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

    return None


# ---------------------------------------------------------------------------
# File card widget
# ---------------------------------------------------------------------------

class _FileCard(QtWidgets.QFrame):
    """Clickable card showing a file thumbnail and its name."""

    def __init__(self, filepath, on_opened=None, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._on_opened = on_opened

        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedWidth(_CARD_W)
        self.setToolTip(filepath)

        tc = _get_theme_colors()
        self.setStyleSheet(
            f"_FileCard {{ background: {tc['card_bg']}; border: 1px solid {tc['card_border']}; border-radius: 4px; }}"
            f"_FileCard:hover {{ border: 1px solid {tc['accent']}; }}"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ---- thumbnail ----
        thumb = QtWidgets.QLabel()
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumb.setFixedSize(_THUMB_W, _THUMB_H)
        thumb.setStyleSheet(f"border: 1px solid {tc['thumb_border']}; background: {tc['thumb_bg']}; border-radius: 3px;")

        pix = _thumbnail_pixmap(filepath)
        if pix:
            thumb.setPixmap(pix)
        else:
            icon = QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            thumb.setPixmap(icon.pixmap(48, 48))

        layout.addWidget(thumb)

        # ---- filename label (extension stripped for readability) ----
        name = os.path.splitext(os.path.basename(filepath))[0]
        lbl = QtWidgets.QLabel(name)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setFixedWidth(_CARD_W - 12)
        lbl.setStyleSheet(f"font-size: 11px; color: {tc['text']};")
        layout.addWidget(lbl)

        # ---- file-type badge ----
        ext_badge = QtWidgets.QLabel(os.path.splitext(filepath)[1].upper().lstrip("."))
        ext_badge.setAlignment(QtCore.Qt.AlignCenter)
        ext_badge.setFixedWidth(_CARD_W - 12)
        ext_badge.setStyleSheet(f"font-size: 9px; color: {tc['badge']}; font-style: italic;")
        layout.addWidget(ext_badge)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            ext = os.path.splitext(self.filepath)[1].lower()
            if ext == ".fcstd":
                _path = self.filepath
                if self._on_opened:
                    self._on_opened()
                def _open_fcstd(path=_path):
                    try:
                        print(f"KM-FreeCAD StartPage: Opening '{path}' in FreeCAD...")
                        FreeCAD.openDocument(path)
                        _add_recent_file(path)
                    except Exception as exc:
                        FreeCAD.Console.PrintWarning(
                            f"KM-FreeCAD StartPage: Could not open '{path}': {exc}\n"
                        )
                QtCore.QTimer.singleShot(0, _open_fcstd)
            elif ext in _FREECAD_EXT:
                module = _resolve_module(self.filepath)
                if module is not None:
                    _path = self.filepath
                    if self._on_opened:
                        self._on_opened()
                    QtCore.QTimer.singleShot(0, lambda p=_path, m=module: _load_in_freecad(p, m))
            else:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.filepath))
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setFrameStyle(QtWidgets.QFrame.Box | QtWidgets.QFrame.Plain)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# Lesson row
# ---------------------------------------------------------------------------

def _build_lesson_widget(lesson_name, lesson_path, on_file_opened=None):
    """Return a widget for one lesson, or None if there are no displayable files."""
    files = sorted(
        f for f in os.listdir(lesson_path)
        if (
            os.path.isfile(os.path.join(lesson_path, f))
            and not f.startswith(".")
            and os.path.splitext(f)[1].lower() in _SHOW_EXT
        )
    )
    if not files:
        return None

    tc = _get_theme_colors()
    widget = QtWidgets.QWidget()
    vbox = QtWidgets.QVBoxLayout(widget)
    vbox.setContentsMargins(8, 2, 8, 8)
    vbox.setSpacing(6)

    lbl = QtWidgets.QLabel(lesson_name)
    lbl.setStyleSheet(
        f"font-size: 12px; font-weight: bold;"
        f" border-bottom: 2px solid {tc['accent']}; padding-bottom: 3px; margin-bottom: 4px;"
    )
    vbox.addWidget(lbl)

    cards_row = QtWidgets.QWidget()
    row_layout = QtWidgets.QHBoxLayout(cards_row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(10)
    row_layout.setAlignment(QtCore.Qt.AlignLeft)

    for filename in files:
        card = _FileCard(os.path.join(lesson_path, filename), on_opened=on_file_opened)
        row_layout.addWidget(card)

    row_layout.addStretch()
    vbox.addWidget(cards_row)
    return widget


# ---------------------------------------------------------------------------
# Class section
# ---------------------------------------------------------------------------

def _build_class_section(class_name, class_path, on_file_opened=None):
    """Return a framed widget for one class with an explicit title label."""
    tc = _get_theme_colors()
    frame = QtWidgets.QFrame()
    frame.setObjectName("kmClassSection")
    frame.setStyleSheet(
        f"QFrame#kmClassSection {{ border: 2px solid {tc['accent']}; border-radius: 6px; }}"
        "QFrame#kmClassSection > QWidget { border: none; }"
        "QFrame#kmClassSection > QLabel { border: none; }"
    )

    outer = QtWidgets.QVBoxLayout(frame)
    outer.setSpacing(4)
    outer.setContentsMargins(10, 8, 10, 10)

    # Class title label at the top of the frame
    title_lbl = QtWidgets.QLabel(class_name)
    title_lbl.setStyleSheet(
        f"font-size: 14px; font-weight: bold; color: {tc['accent']}; border: none; padding: 2px 0;"
    )
    outer.addWidget(title_lbl)

    # Thin separator under the title
    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.HLine)
    sep.setStyleSheet(f"border: none; background: {tc['accent']}; max-height: 1px; margin-bottom: 4px;")
    outer.addWidget(sep)

    lessons = sorted(
        d for d in os.listdir(class_path)
        if os.path.isdir(os.path.join(class_path, d)) and not d.startswith(".")
    )

    lesson_added = False
    for lesson_name in lessons:
        lesson_widget = _build_lesson_widget(
            lesson_name, os.path.join(class_path, lesson_name), on_file_opened
        )
        if lesson_widget:
            outer.addWidget(lesson_widget)
            lesson_added = True

    if not lesson_added:
        outer.addWidget(QtWidgets.QLabel("  (no files found)"))

    return frame


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class StartPage(QtWidgets.QDialog):
    """Startup page listing all Knox Makers FreeCAD classes and lesson files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Knox Makers - Start Page")
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog
        )
        self.resize(980, 720)
        self._drag_pos = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- header bar (also acts as drag handle) ----
        tc = _get_theme_colors()
        header = QtWidgets.QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {tc['hdr_bg']};")
        header.setCursor(QtCore.Qt.SizeAllCursor)
        header.mousePressEvent   = self._on_header_press
        header.mouseMoveEvent    = self._on_header_move
        header.mouseReleaseEvent = self._on_header_release
        h_layout = QtWidgets.QHBoxLayout(header)
        h_layout.setContentsMargins(16, 8, 16, 8)
        h_layout.setSpacing(12)

        logo_path = os.path.join(_ADDON_DIR, "icons", "KnoxMakers.svg")
        if os.path.exists(logo_path):
            logo_lbl = QtWidgets.QLabel()
            pix = QtGui.QPixmap(logo_path)
            if not pix.isNull():
                logo_lbl.setPixmap(
                    pix.scaled(36, 36, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                )
            h_layout.addWidget(logo_lbl)

        title_lbl = QtWidgets.QLabel("Knox Makers - Start Page")
        title_lbl.setStyleSheet(f"color: {tc['hdr_title']}; font-size: 17px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        # do not remove below
        # path_lbl = QtWidgets.QLabel(CLASSES_DIR)
        # path_lbl.setStyleSheet(f"color: {tc['hdr_path']}; font-size: 10px;")
        # h_layout.addWidget(path_lbl)

        # Close (×) button in the header
        close_hdr_btn = QtWidgets.QPushButton("\u00d7")
        close_hdr_btn.setFixedSize(32, 32)
        close_hdr_btn.setStyleSheet(
            f"QPushButton {{ color: {tc['hdr_btn_fg']}; background: transparent;"
            " border: none; font-size: 20px; font-weight: bold; }"
            f"QPushButton:hover {{ background: rgba(128,128,128,0.3); color: {tc['hdr_btn_fg']}; border-radius: 4px; }}"
        )
        close_hdr_btn.clicked.connect(self.close)
        h_layout.addWidget(close_hdr_btn)

        outer.addWidget(header)

        # ---- scroll area ----
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer.addWidget(scroll)

        container = QtWidgets.QWidget()
        scroll.setWidget(container)

        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setSpacing(24)
        vbox.setContentsMargins(16, 24, 16, 16)

        if not os.path.isdir(CLASSES_DIR):
            msg = QtWidgets.QLabel(
                f"<b>Classes directory not found:</b><br>"
                f"<code>{CLASSES_DIR}</code><br><br>"
                "Run the Knox Makers addon installer to set up your class files."
            )
            msg.setTextFormat(QtCore.Qt.RichText)
            msg.setStyleSheet("padding: 20px; border-radius: 6px;")
            vbox.addWidget(msg)
            vbox.addStretch()
        else:
            classes = sorted(
                d for d in os.listdir(CLASSES_DIR)
                if os.path.isdir(os.path.join(CLASSES_DIR, d)) and not d.startswith(".")
            )

            if not classes:
                vbox.addWidget(QtWidgets.QLabel("No class folders found in Classes directory."))
                vbox.addStretch()
            else:
                for class_name in classes:
                    section = _build_class_section(
                        class_name,
                        os.path.join(CLASSES_DIR, class_name),
                        on_file_opened=self.close,
                    )
                    vbox.addWidget(section)
                vbox.addStretch()

        # ---- close button row ----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 8)
        btn_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Drag support for frameless window
    # ------------------------------------------------------------------

    def _on_header_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _on_header_move(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def _on_header_release(self, event):
        self._drag_pos = None


# ---------------------------------------------------------------------------
# Entry point called from InitGui.py
# ---------------------------------------------------------------------------

def show_start_page():
    """Create and show the StartPage dialog attached to FreeCAD's main window."""
    try:
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        page = StartPage(mw)
        try:
            geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        except AttributeError:
            geo = QtWidgets.QApplication.desktop().availableGeometry()
        page.move(
            geo.x() + (geo.width() - page.width()) // 2,
            geo.y() + (geo.height() - page.height()) // 2,
        )
        page.show()
        FreeCAD.Console.PrintLog("KM-FreeCAD: Start page displayed.\n")
    except Exception as exc:
        FreeCAD.Console.PrintWarning(f"KM-FreeCAD: Could not show start page: {exc}\n")
