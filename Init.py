# -*- coding: utf-8 -*-
"""Knox Makers FreeCAD Manager Init: Auto-update using FreeCAD AddonManager API."""

import sys
import os
import inspect
import FreeCAD

# locate this Init.py
_this_file = inspect.getfile(inspect.currentframe())
addon_dir = os.path.dirname(_this_file)
FreeCAD.Console.PrintMessage(f"- Init running from: {addon_dir}\n")

# make sure we can import install.py
if addon_dir not in sys.path:
    sys.path.insert(0, addon_dir)


def get_metadata(addon_dir=addon_dir):
    """Parse package.xml to get addon metadata including repository URL and branch."""
    import xml.etree.ElementTree as ET

    package_xml_path = os.path.join(addon_dir, "package.xml")
    if not os.path.exists(package_xml_path):
        return None, None, None

    try:
        tree = ET.parse(package_xml_path)
        root = tree.getroot()

        # Handle XML namespace
        ns = {'pkg': 'https://wiki.freecad.org/Package_Metadata'}

        name = root.find('pkg:name', ns)
        addon_name = "KM-FreeCAD"

        url_elem = root.find("pkg:url[@type='repository']", ns)
        print(
            f"Parsed package.xml: name={addon_name}, repo_url={url_elem.text if url_elem is not None else 'N/A'}, branch={url_elem.get('branch', 'main') if url_elem is not None else 'N/A'}"
        )
        if url_elem is not None:
            repo_url = url_elem.text
            branch = url_elem.get('branch', 'main')
            print(
                f"Parsed metadata from package.xml: name={addon_name}, repo_url={repo_url}, branch={branch}"
            )
            return addon_name, repo_url, branch
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"Could not parse package.xml: {e}\n")

    return None, None, None


addon_name, repo_url, branch = get_metadata(addon_dir)

# Allow branch override via preferences (useful for tracking dev/testing branches)
prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager")
branch_override = prefs.GetString("BranchOverride", "")
if branch_override:
    FreeCAD.Console.PrintMessage(f"- Using branch override: {branch_override}\n")
    branch = branch_override


def check_latest_commit(addon_name=addon_name, repo_url=repo_url, branch=branch):
    """Check for the latest commit hash from GitHub API."""

    if not repo_url:
        FreeCAD.Console.PrintWarning("- Could not determine repository URL from package.xml\n")
        return "unknown"

    FreeCAD.Console.PrintMessage(f"- Repository: {repo_url} (branch: {branch})\n")

    try:
        import urllib.request
        import re
        import json

        # Extract owner/repo from URL
        match = re.search(r'github\.com[/:]([^/]+)/([^/\.]+)', repo_url)
        if not match:
            FreeCAD.Console.PrintWarning("- Could not parse GitHub URL\n")
            return "unknown"

        owner, repo = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"

        FreeCAD.Console.PrintMessage(f"- Checking GitHub API for latest commit...\n")

        # Make HTTP request to GitHub API
        req = urllib.request.Request(api_url)
        req.add_header('User-Agent', 'FreeCAD-KnoxMakers-Manager')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            full_hash = data.get('sha', 'unknown')
            short_hash = full_hash[:7]
            FreeCAD.Console.PrintMessage(f"- Latest GitHub commit: {short_hash}\n")
            return short_hash

    except Exception as e:
        FreeCAD.Console.PrintWarning(f"- Error checking for updates: {e}\n")
        return "unknown"


# Check for the latest commit using AddonManager utilities
current_hash = check_latest_commit(addon_dir)

# load stored hash from prefs
prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager")
last_hash = prefs.GetString("LastInstalledHash", "")
FreeCAD.Console.PrintMessage(f"- Last installed: {last_hash}\n")

# check FreeCAD version
version = FreeCAD.Version()
major = int(version[0])
minor = int(version[1])
current_version = f"v{major}-{minor}"

# check installed version history
installed_versions = prefs.GetString("InstalledVersions", "")
FreeCAD.Console.PrintMessage(f"- FreeCAD version: {current_version}\n")
FreeCAD.Console.PrintMessage(f"- Installed for versions: {installed_versions or 'none'}\n")

# parse version list and check if current version has been installed
version_list = [v.strip() for v in installed_versions.split(",") if v.strip()]
version_already_installed = current_version in version_list

# Check if migration was detected (path changed due to versioned directory migration)
migration_detected = prefs.GetBool("MigrationDetected", False)
if migration_detected:
    FreeCAD.Console.PrintMessage("- Migration detected, forcing reinstall\n")

# run installer if:
# - hash changed (new addon version), OR
# - version not yet installed (FreeCAD upgraded), OR
# - migration was detected (directory structure changed)
needs_install = last_hash != current_hash or not version_already_installed or migration_detected

def _self_update_zip(zip_url, target_dir):
    """Download zip, pre-clean what we can, then overwrite in-place.

    Pre-cleanup: walk target_dir and delete every file/subdir we can.
    Files Python holds open (.pyc etc.) will fail silently and be overwritten
    by the subsequent copytree call — which Windows does allow even on open files.
    This removes stale files that are no longer in the new release.
    """
    import urllib.request
    import tempfile
    import zipfile
    import shutil

    # Pre-cleanup: delete everything we can before the overlay.
    # Locked files (e.g. __pycache__/*.pyc) are skipped silently and overwritten
    # by copytree below, which succeeds even when the file is open on Windows.
    if os.path.isdir(target_dir):
        FreeCAD.Console.PrintMessage(f"- Pre-cleaning addon directory...\n")
        for root, dirs, files in os.walk(target_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass  # locked — will be overwritten by copytree
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass  # not empty (locked files still inside) — leave it

    FreeCAD.Console.PrintMessage(f"- Downloading {zip_url}...\n")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
        tmp = f.name
    try:
        urllib.request.urlretrieve(zip_url, tmp)
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(tmp, 'r') as zf:
                zf.extractall(td)
            # GitHub wraps content in a repo-branch/ subdirectory — unwrap it
            entries = [e for e in os.listdir(td) if os.path.isdir(os.path.join(td, e))]
            src = os.path.join(td, entries[0]) if len(entries) == 1 else td
            shutil.copytree(src, target_dir, dirs_exist_ok=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


if needs_install:
    try:
        # Update the addon from GitHub
        FreeCAD.Console.PrintMessage(f"- Updating addon from GitHub...\n")

        # Build the zip URL from package.xml metadata
        if repo_url and 'github.com' in repo_url:
            clean_url = repo_url.replace('git@github.com:', 'https://github.com/')
            if clean_url.endswith('.git'):
                clean_url = clean_url[:-4]
            zip_url = f"{clean_url}/archive/refs/heads/{branch}.zip"
        else:
            zip_url = repo_url

        _self_update_zip(zip_url, addon_dir)

        FreeCAD.Console.PrintMessage(f"- Addon updated successfully\n")

        # Now run the install to copy files to user directories
        import install

        # Clear migration flag AFTER install runs, so any flag set by install.py
        # during this run doesn't persist and cause a redundant reinstall on next start.
        prefs.SetBool("MigrationDetected", False)

        prefs.SetString("LastInstalledHash", current_hash)

        # add current version to history if not already present
        if current_version not in version_list:
            version_list.append(current_version)
            prefs.SetString("InstalledVersions", ",".join(version_list))

        FreeCAD.Console.PrintMessage(
            f"✓ Knox Makers FreeCAD Manager: Installed commit {current_hash} for {current_version}\n"
        )

        import subprocess

        try:
            FreeCAD.saveParameter()  # Ensure all preferences are saved before restarting

            # Get the application arguments (without the executable)
            args = sys.argv[1:]

            # Determine the correct executable path based on the environment
            appimage = os.getenv("APPIMAGE")

            if appimage:
                # For AppImage, use the APPIMAGE environment variable
                executable = appimage
            else:
                # For normal installations, use sys.executable
                executable = sys.executable

            # Start a new process with the same arguments
            subprocess.Popen([executable] + args)

            # Exit cleanly
            os._exit(0)

        except Exception as e:
            FreeCAD.Console.PrintError(f"✗ Knox Makers FreeCAD Manager restart error: {str(e)}\n")

    except Exception as e:
        FreeCAD.Console.PrintError(f"✗ Knox Makers FreeCAD Manager install error: {e}\n")
else:
    FreeCAD.Console.PrintMessage(
        f"✓ Knox Makers FreeCAD Manager: Already installed ({current_hash} for {current_version})\n"
    )
