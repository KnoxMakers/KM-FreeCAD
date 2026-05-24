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

_THUMB_W = 150
_THUMB_H = 120
_CARD_W  = 170

# Addon directory (used to locate icon assets)
_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


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

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath

        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedWidth(_CARD_W)
        self.setToolTip(filepath)
        self.setStyleSheet(
            "_FileCard { background: #f9f9f9; border-radius: 4px; }"
            "_FileCard:hover { background: #e8f4fd; border: 1px solid #3498db; }"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ---- thumbnail ----
        thumb = QtWidgets.QLabel()
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumb.setFixedSize(_THUMB_W, _THUMB_H)
        thumb.setStyleSheet("border: 1px solid #ccc; background: #efefef; border-radius: 3px;")

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
        lbl.setStyleSheet("font-size: 11px; color: #333;")
        layout.addWidget(lbl)

        # ---- file-type badge ----
        ext_badge = QtWidgets.QLabel(os.path.splitext(filepath)[1].upper().lstrip("."))
        ext_badge.setAlignment(QtCore.Qt.AlignCenter)
        ext_badge.setFixedWidth(_CARD_W - 12)
        ext_badge.setStyleSheet(
            "font-size: 9px; color: #666; font-style: italic;"
        )
        layout.addWidget(ext_badge)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            ext = os.path.splitext(self.filepath)[1].lower()
            if ext == ".fcstd":
                try:
                    FreeCAD.openDocument(self.filepath)
                except Exception as exc:
                    FreeCAD.Console.PrintWarning(
                        f"KM-FreeCAD StartPage: Could not open '{self.filepath}': {exc}\n"
                    )
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

def _build_lesson_widget(lesson_name, lesson_path):
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

    widget = QtWidgets.QWidget()
    vbox = QtWidgets.QVBoxLayout(widget)
    vbox.setContentsMargins(8, 2, 8, 8)
    vbox.setSpacing(6)

    lbl = QtWidgets.QLabel(lesson_name)
    lbl.setStyleSheet(
        "font-size: 12px; font-weight: bold; color: #555; "
        "border-bottom: 1px solid #ddd; padding-bottom: 2px;"
    )
    vbox.addWidget(lbl)

    cards_row = QtWidgets.QWidget()
    row_layout = QtWidgets.QHBoxLayout(cards_row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(10)
    row_layout.setAlignment(QtCore.Qt.AlignLeft)

    for filename in files:
        card = _FileCard(os.path.join(lesson_path, filename))
        row_layout.addWidget(card)

    row_layout.addStretch()
    vbox.addWidget(cards_row)
    return widget


# ---------------------------------------------------------------------------
# Class section
# ---------------------------------------------------------------------------

def _build_class_section(class_name, class_path):
    """Return a collapsible QGroupBox for one class."""
    group = QtWidgets.QGroupBox(class_name)
    group.setCheckable(True)
    group.setChecked(True)
    group.setStyleSheet(
        "QGroupBox {"
        "  font-size: 14px; font-weight: bold;"
        "  border: 2px solid #c0392b;"
        "  border-radius: 6px;"
        "  margin-top: 12px;"
        "  padding-top: 6px;"
        "}"
        "QGroupBox::title {"
        "  subcontrol-origin: margin;"
        "  left: 14px;"
        "  color: #c0392b;"
        "  padding: 0 4px;"
        "}"
        "QGroupBox::indicator { width: 14px; height: 14px; }"
    )

    inner = QtWidgets.QWidget()
    group_layout = QtWidgets.QVBoxLayout(group)
    group_layout.setSpacing(4)
    group_layout.setContentsMargins(4, 4, 4, 8)

    inner_layout = QtWidgets.QVBoxLayout(inner)
    inner_layout.setContentsMargins(0, 0, 0, 0)
    inner_layout.setSpacing(4)

    lessons = sorted(
        d for d in os.listdir(class_path)
        if os.path.isdir(os.path.join(class_path, d)) and not d.startswith(".")
    )

    lesson_added = False
    for lesson_name in lessons:
        lesson_widget = _build_lesson_widget(lesson_name, os.path.join(class_path, lesson_name))
        if lesson_widget:
            inner_layout.addWidget(lesson_widget)
            lesson_added = True

    if not lesson_added:
        inner_layout.addWidget(QtWidgets.QLabel("  (no files found)"))

    group_layout.addWidget(inner)

    # Toggle visibility of inner widget when the checkbox is clicked
    group.toggled.connect(inner.setVisible)

    return group


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class StartPage(QtWidgets.QDialog):
    """Startup page listing all Knox Makers FreeCAD classes and lesson files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Knox Makers – FreeCAD Classes")
        self.setWindowFlags(
            self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        )
        self.resize(980, 720)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- header bar ----
        header = QtWidgets.QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("background: #1a1a2e;")
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

        title_lbl = QtWidgets.QLabel("Knox Makers  ·  FreeCAD Classes")
        title_lbl.setStyleSheet("color: #ffffff; font-size: 17px; font-weight: bold;")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        path_lbl = QtWidgets.QLabel(CLASSES_DIR)
        path_lbl.setStyleSheet("color: #aaaacc; font-size: 10px;")
        h_layout.addWidget(path_lbl)

        outer.addWidget(header)

        # ---- scroll area ----
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #f0f0f0; }")
        outer.addWidget(scroll)

        container = QtWidgets.QWidget()
        container.setStyleSheet("background: #f0f0f0;")
        scroll.setWidget(container)

        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setSpacing(12)
        vbox.setContentsMargins(16, 16, 16, 16)

        if not os.path.isdir(CLASSES_DIR):
            msg = QtWidgets.QLabel(
                f"<b>Classes directory not found:</b><br>"
                f"<code>{CLASSES_DIR}</code><br><br>"
                "Run the Knox Makers addon installer to set up your class files."
            )
            msg.setTextFormat(QtCore.Qt.RichText)
            msg.setStyleSheet("padding: 20px; background: white; border-radius: 6px;")
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
                    section = _build_class_section(class_name, os.path.join(CLASSES_DIR, class_name))
                    vbox.addWidget(section)
                vbox.addStretch()

        # ---- footer / close button ----
        footer = QtWidgets.QWidget()
        footer.setFixedHeight(44)
        footer.setStyleSheet("background: #e8e8e8; border-top: 1px solid #ccc;")
        f_layout = QtWidgets.QHBoxLayout(footer)
        f_layout.setContentsMargins(16, 4, 16, 4)
        f_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        f_layout.addWidget(close_btn)
        outer.addWidget(footer)


# ---------------------------------------------------------------------------
# Entry point called from InitGui.py
# ---------------------------------------------------------------------------

def show_start_page():
    """Create and show the StartPage dialog attached to FreeCAD's main window."""
    try:
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        page = StartPage(mw)
        page.show()
        FreeCAD.Console.PrintLog("KM-FreeCAD: Start page displayed.\n")
    except Exception as exc:
        FreeCAD.Console.PrintWarning(f"KM-FreeCAD: Could not show start page: {exc}\n")
