# -*- coding: utf-8 -*-
"""
KM-FreeCAD InitGui: Checks for new cam+ FreeCAD builds and alerts the user.

Runs after the FreeCAD GUI is fully initialised, making it safe to show dialogs.

Version comparison handles:
  v1.1rc3-cam+2  →  (1, 1, rc=3, build=2)
  v1.1-cam+1     →  (1, 1, rc=None, build=1)   ← full release > any RC
  v1.2rc1-cam+1  →  (1, 2, rc=1, build=1)

Comparison order: major → minor → rc (None=release > int=rc) → build#
When the rc level is the same and build# is unknown locally, the GitHub
release's published_at date is compared to FreeCAD's BuildRevisionDate.
"""

import FreeCAD

# ---------------------------------------------------------------------------
# Configuration — edit _CAMPLUS_REPO to match your FreeCAD fork's GitHub path
# Users can also override via FreeCAD prefs key "CamPlusRepo".
# ---------------------------------------------------------------------------
_CAMPLUS_REPO = "Connor9220/FreeCAD"
_PREFS_PATH = "User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager"
_CHECK_INTERVAL_SECS = 86400  # re-check at most once every 24 hours


# ---------------------------------------------------------------------------
# Main check — all helpers are defined as nested functions so there are no
# module-level name lookups when QTimer fires the callback.  FreeCAD exec()s
# this file rather than importing it, so module globals are not available in
# deferred callbacks; nesting guarantees a true closure.
# ---------------------------------------------------------------------------


def check_for_freecad_update(
    _repo=_CAMPLUS_REPO,
    _prefs_path=_PREFS_PATH,
    _check_interval=_CHECK_INTERVAL_SECS,
):
    import re
    import time
    import json
    import webbrowser
    import urllib.request
    import urllib.parse
    from PySide import QtWidgets, QtCore

    # --- helpers (nested so they close over nothing external) ---------------

    def parse_tag(tag):
        m = re.match(r'^v?(\d+)\.(\d+)(?:\.(\d+))?(?:rc(\d+))?-?cam\+(\d+)$', tag.strip())
        if not m:
            return None
        return (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)) if m.group(3) else 0,    # patch, default 0
            int(m.group(4)) if m.group(4) else None,  # None = full release
            int(m.group(5)),
        )

    def cmp_tags(tag_a, tag_b):
        a = parse_tag(tag_a)
        b = parse_tag(tag_b)
        if a is None or b is None:
            return 0
        for i in (0, 1, 2):  # major, minor, patch
            if a[i] != b[i]:
                return a[i] - b[i]
        a_rc, b_rc = a[3], b[3]
        if a_rc is None and b_rc is not None:
            return 1  # full release > RC
        if a_rc is not None and b_rc is None:
            return -1  # RC < full release
        if a_rc != b_rc:
            return a_rc - b_rc  # both are ints here
        return a[4] - b[4]

    def running_version_info():
        try:
            ver = FreeCAD.Version()
            major = int(ver[0]) if ver[0].isdigit() else 0
            minor = int(ver[1]) if ver[1].isdigit() else 0
        except Exception:
            return None
        try:
            suffix = FreeCAD.ConfigGet("BuildVersionSuffix")
        except Exception:
            suffix = ""
        branch = ver[6] if len(ver) > 6 else ""
        is_camplus = "cam+" in suffix or "cam+" in branch
        rc_match = re.search(r'rc(\d+)', suffix)
        rc = int(rc_match.group(1)) if rc_match else None
        build_date = None
        try:
            date_str = ver[5].split()[0]
            parts = date_str.split("/")
            build_date = (int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            pass
        rc_str = f"rc{rc}" if rc is not None else ""
        approx_tag = f"v{major}.{minor}{rc_str}-cam+0"
        return {
            "major": major,
            "minor": minor,
            "rc": rc,
            "build_date": build_date,
            "is_camplus": is_camplus,
            "approx_tag": approx_tag,
        }

    def is_newer_than_running(info, latest_tag, published_at):
        if info is None or not info["is_camplus"]:
            return False
        cmp = cmp_tags(latest_tag, info["approx_tag"])
        if cmp > 0:
            lp = parse_tag(latest_tag)
            rp = parse_tag(info["approx_tag"])
            if lp and rp and lp[:3] == rp[:3]:
                # Same major.minor.rc — fall back to release date vs build date
                m = re.match(r'(\d{4})-(\d{2})-(\d{2})', published_at)
                rel_date = (
                    (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
                )
                local_date = info["build_date"]
                return rel_date > local_date if (rel_date and local_date) else False
            return True
        return False

    def show_update_dialog(info, latest_tag, release_url, prefs):
        try:
            current_desc = (
                info["approx_tag"].replace("-cam+0", "-cam+?") if info else "unknown"
            )
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("New cam+ FreeCAD Build Available")
            msg.setIcon(QtWidgets.QMessageBox.Information)
            msg.setText(
                f"<b>A new cam+ FreeCAD build is available!</b><br><br>"
                f"Latest release: <b>{latest_tag}</b><br>"
                f"Currently running: <b>{current_desc}</b><br><br>"
                f"Download the new AppImage from the Knox Makers FreeCAD releases page:<br>"
                f"<code>{release_url}</code>"
            )
            msg.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            download_btn = msg.addButton(
                "Open Download Page", QtWidgets.QMessageBox.AcceptRole
            )
            msg.addButton("Remind Me Later", QtWidgets.QMessageBox.RejectRole)
            dismiss_btn = msg.addButton(
                "Dismiss for This Release", QtWidgets.QMessageBox.DestructiveRole
            )
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == download_btn:
                webbrowser.open(release_url)
            elif clicked == dismiss_btn:
                prefs.SetString("DismissedUpdateTag", latest_tag)
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                f"KM-FreeCAD: Could not show update dialog: {e}\n"
            )

    # --- main logic ---------------------------------------------------------

    info = running_version_info()
    if not info or not info["is_camplus"]:
        FreeCAD.Console.PrintLog(
            "KM-FreeCAD: Not a cam+ build – update check skipped.\n"
        )
        return

    prefs = FreeCAD.ParamGet(_prefs_path)
    repo = prefs.GetString("CamPlusRepo", _repo)

    last_check = prefs.GetInt("LastCamPlusUpdateCheck", 0)
    if time.time() - last_check < _check_interval:
        return

    try:
        # Use /releases list so we can filter for cam+ tags; the repo also
        # publishes weekly non-cam+ builds that would appear via /releases/latest.
        url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "KM-FreeCAD-UpdateChecker/1.0")

        with urllib.request.urlopen(req, timeout=6) as resp:
            releases = json.loads(resp.read().decode())

        prefs.SetInt("LastCamPlusUpdateCheck", int(time.time()))

        best = None
        for rel in releases:
            tag = rel.get("tag_name", "").strip()
            if not tag or parse_tag(tag) is None:
                continue
            if best is None or cmp_tags(tag, best.get("tag_name", "")) > 0:
                best = rel

        if best is None:
            FreeCAD.Console.PrintLog(
                "KM-FreeCAD: No cam+ releases found in recent list.\n"
            )
            return

        latest_tag = best.get("tag_name", "").strip()
        published_at = best.get("published_at", "")
        release_url = urllib.parse.unquote(
            best.get("html_url", f"https://github.com/{repo}/releases")
        )

        dismissed = prefs.GetString("DismissedUpdateTag", "")
        if dismissed and cmp_tags(latest_tag, dismissed) <= 0:
            return

        if is_newer_than_running(info, latest_tag, published_at):
            FreeCAD.Console.PrintMessage(
                f"KM-FreeCAD: New cam+ build available → {latest_tag}\n"
            )
            show_update_dialog(info, latest_tag, release_url, prefs)
        else:
            FreeCAD.Console.PrintLog(
                f"KM-FreeCAD: cam+ is up to date (latest: {latest_tag})\n"
            )

    except Exception as e:
        FreeCAD.Console.PrintWarning(f"KM-FreeCAD: Update check error: {e}\n")


# ---------------------------------------------------------------------------
# Schedule the check to run 2 seconds after the GUI finishes loading.
# Using QTimer.singleShot keeps startup fast and avoids blocking the main thread.
# ---------------------------------------------------------------------------
try:
    from PySide.QtCore import QTimer

    QTimer.singleShot(2000, check_for_freecad_update)
    FreeCAD.Console.PrintLog("KM-FreeCAD: cam+ update check scheduled.\n")

except Exception as e:
    FreeCAD.Console.PrintWarning(f"KM-FreeCAD: Could not schedule update check: {e}\n")
