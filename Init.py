# -*- coding: utf-8 -*-
"""Knox Makers FreeCAD Manager Init: Auto-update using FreeCAD AddonManager API."""

import sys
import os
import inspect
import FreeCAD

# locate this Init.py
_this_file = inspect.getfile(inspect.currentframe())
addon_dir = os.path.dirname(_this_file)
FreeCAD.Console.PrintMessage(f"– Init running from: {addon_dir}\n")

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
prefs = FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager"
)
branch_override = prefs.GetString("BranchOverride", "")
if branch_override:
    FreeCAD.Console.PrintMessage(f"– Using branch override: {branch_override}\n")
    branch = branch_override


def check_latest_commit(addon_name=addon_name, repo_url=repo_url, branch=branch):
    """Check for the latest commit hash from GitHub API."""

    if not repo_url:
        FreeCAD.Console.PrintWarning(
            "– Could not determine repository URL from package.xml\n"
        )
        return "unknown"

    FreeCAD.Console.PrintMessage(f"– Repository: {repo_url} (branch: {branch})\n")

    try:
        import urllib.request
        import re
        import json

        # Extract owner/repo from URL
        match = re.search(r'github\.com[/:]([^/]+)/([^/\.]+)', repo_url)
        if not match:
            FreeCAD.Console.PrintWarning("– Could not parse GitHub URL\n")
            return "unknown"

        owner, repo = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"

        FreeCAD.Console.PrintMessage(f"– Checking GitHub API for latest commit...\n")

        # Make HTTP request to GitHub API
        req = urllib.request.Request(api_url)
        req.add_header('User-Agent', 'FreeCAD-KnoxMakers-Manager')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            full_hash = data.get('sha', 'unknown')
            short_hash = full_hash[:7]
            FreeCAD.Console.PrintMessage(f"– Latest GitHub commit: {short_hash}\n")
            return short_hash

    except Exception as e:
        FreeCAD.Console.PrintWarning(f"– Error checking for updates: {e}\n")
        return "unknown"


# Check for the latest commit using AddonManager utilities
current_hash = check_latest_commit(addon_dir)

# load stored hash from prefs
prefs = FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager"
)
last_hash = prefs.GetString("LastInstalledHash", "")
FreeCAD.Console.PrintMessage(f"– Last installed: {last_hash}\n")

# check FreeCAD version
version = FreeCAD.Version()
major = int(version[0])
minor = int(version[1])
current_version = f"v{major}-{minor}"

# check installed version history
installed_versions = prefs.GetString("InstalledVersions", "")
FreeCAD.Console.PrintMessage(f"– FreeCAD version: {current_version}\n")
FreeCAD.Console.PrintMessage(
    f"– Installed for versions: {installed_versions or 'none'}\n"
)

# parse version list and check if current version has been installed
version_list = [v.strip() for v in installed_versions.split(",") if v.strip()]
version_already_installed = current_version in version_list

# run installer if hash changed OR version not yet installed
needs_install = last_hash != current_hash or not version_already_installed

if needs_install:
    try:
        # Update the addon from GitHub using AddonManager
        FreeCAD.Console.PrintMessage(f"– Updating addon from GitHub...\n")

        # Ensure FreeCAD.GuiUp exists (may not exist in some FreeCAD versions/contexts)
        if not hasattr(FreeCAD, 'GuiUp'):
            FreeCAD.GuiUp = False

        from addonmanager_installer import AddonInstaller

        # Create a simple Addon-like object for the installer
        class AddonObject:
            def __init__(self, name, url, branch):
                self.name = name
                self.url = url
                self.branch = branch

            def get_zip_url(self):
                """Return the GitHub zip download URL for this addon."""
                # Handle both https://github.com/owner/repo and git@github.com:owner/repo formats
                if 'github.com' in self.url:
                    clean_url = self.url.replace(
                        'git@github.com:', 'https://github.com/'
                    )
                    if clean_url.endswith('.git'):
                        clean_url = clean_url[:-4]
                    return f"{clean_url}/archive/refs/heads/{self.branch}.zip"
                return self.url

        addon_obj = AddonObject(addon_name, repo_url, branch)
        installer = AddonInstaller(addon_obj)
        installer.run()

        FreeCAD.Console.PrintMessage(f"– Addon updated successfully\n")

        # Now run the install to copy files to user directories
        import install

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
            FreeCAD.Console.PrintError(
                f"✗ Knox Makers FreeCAD Manager restart error: {str(e)}\n"
            )

    except Exception as e:
        FreeCAD.Console.PrintError(
            f"✗ Knox Makers FreeCAD Manager install error: {e}\n"
        )
else:
    FreeCAD.Console.PrintMessage(
        f"✓ Knox Makers FreeCAD Manager: Already installed ({current_hash} for {current_version})\n"
    )
