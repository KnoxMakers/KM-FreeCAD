import FreeCAD, os, shutil, json

# Get FreeCAD preferences
prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/CAM")
addon_prefs = FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/KnoxMakersFreeCADManager"
)

# Get user's home directory
home_dir = os.path.expanduser("~")
freecad_dir = os.path.join(home_dir, "Documents", "FreeCAD")

# Check FreeCAD version
version = FreeCAD.Version()
major = int(version[0])
minor = int(version[1])
version_string = f"v{major}-{minor}"  # e.g., v1-1, v1-2

# Detect CAM+ custom build - uses v1.2 toolbit files even on v1.1
# CAM+ builds set PACKAGE_VERSION_SUFFIX="cam+" in CMakeLists.txt
is_cam_plus_build = False
source_version_override = None
try:
    # Check BuildVersionSuffix from Config (set via CMake PACKAGE_VERSION_SUFFIX)
    # This works for both local builds and AppImage builds
    build_suffix = FreeCAD.ConfigGet("BuildVersionSuffix")
    if "cam+" in build_suffix.lower():
        is_cam_plus_build = True
        print(f"✓ Detected CAM+ custom build (suffix: {build_suffix})")
        # CAM+ v1.1 uses v1.2 toolbit files
        if major == 1 and minor == 1:
            source_version_override = "v1-2"
            print(f"  → Using v1-2 toolbit files for CAM+ v1.1")
    else:
        print(
            f"Detected FreeCAD {version_string} (suffix: {build_suffix if build_suffix else 'none'})"
        )
except Exception as e:
    print(f"Warning: Version detection error: {e}")
    print(f"Assuming standard FreeCAD {version_string}")

# Determine the correct directory structure based on version
if major < 1 or (major == 1 and minor < 1):
    # FreeCAD 1.0.x - use legacy structure without CAMAssets
    freecad_assets_dir = freecad_dir
    source_tools_base = "Tools"  # Source from Tools/ in repo
else:
    # FreeCAD 1.1+ - Use FreeCAD's built-in directory resolution
    # This automatically handles versioned vs non-versioned directories
    base_camassets = os.path.join(freecad_dir, "CAMAssets")

    # Use mostRecentConfigFromBase to get the actual directory (versioned or not)
    try:
        freecad_assets_dir = FreeCAD.ApplicationDirectories.mostRecentConfigFromBase(
            base_camassets
        )
        print(f"Using CAMAssets directory: {freecad_assets_dir}")
    except:
        # Fallback if mostRecentConfigFromBase not available or fails
        freecad_assets_dir = base_camassets
        print(f"Using base CAMAssets directory: {freecad_assets_dir}")

    # Create the directory if it doesn't exist
    if not os.path.exists(freecad_assets_dir):
        os.makedirs(freecad_assets_dir)
        print(f"Created CAMAssets directory at: {freecad_assets_dir}")

    # Determine source directory based on whether we're in versioned structure
    # For CAM+ builds, override the source version
    source_ver = source_version_override if source_version_override else version_string

    if freecad_assets_dir.endswith(version_string):
        # Using versioned structure - source from versioned addon directory
        source_tools_base = os.path.join("CAMAssets", source_ver, "Tools")
        if source_version_override:
            print(f"Using source files from: {source_tools_base}")
    else:
        # Using non-versioned structure - source from base tools
        source_tools_base = "Tools"

# Track the actual install path - if it changes (due to migration), we need to reinstall
last_install_path = addon_prefs.GetString("LastInstallPath", "")
path_changed = last_install_path and last_install_path != freecad_assets_dir
if path_changed:
    print(f"CAMAssets path changed from {last_install_path} to {freecad_assets_dir}")
    print(f"Migration detected - will force reinstall of files")
    # Set a flag that Init.py can check
    addon_prefs.SetBool("MigrationDetected", True)

# Update the last install path
addon_prefs.SetString("LastInstallPath", freecad_assets_dir)

# Define default paths
tool_bit_dir = os.path.join(freecad_assets_dir, "Tools", "Bit")
tool_lib_dir = os.path.join(freecad_assets_dir, "Tools", "Library")
tool_shape_dir = os.path.join(freecad_assets_dir, "Tools", "Shape")
tools_root_dir = os.path.join(freecad_assets_dir, "Tools")  # Root of Tools directory
default_tool_lib_file = os.path.join(tool_lib_dir, "NibblerBOT.fctl")
gcode_dir = os.path.join(freecad_dir, "Gcode")  # Gcode directory
camcheck_dir = os.path.join(freecad_dir, "CAMCheck")  # CamCheck directory
classes_dir = os.path.join(freecad_dir, "Classes")
course_dir = os.path.join(classes_dir, "FreeCAD CAM 101 - Intro to CAM")
lesson1_dir = os.path.join(course_dir, "Lesson 1")
lesson2_dir = os.path.join(course_dir, "Lesson 2")
lesson3_dir = os.path.join(course_dir, "Lesson 3")

# Ensure directories exist
for path in [
    tool_bit_dir,
    tool_lib_dir,
    tool_shape_dir,
    gcode_dir,
    camcheck_dir,
    classes_dir,
    course_dir,
    lesson1_dir,
    lesson2_dir,
    lesson3_dir,
]:
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created directory: {path}")

# Check and set preferences
if not prefs.GetString("LastPathToolBit"):
    prefs.SetString("LastPathToolBit", tool_bit_dir)
    print(f"Set LastPathToolBit to: {tool_bit_dir}")

if not prefs.GetString("LastPathToolLibrary"):
    prefs.SetString("LastPathToolLibrary", tool_lib_dir)
    print(f"Set LastPathToolLibrary to: {tool_lib_dir}")

if not prefs.GetString("LastPathToolShape"):
    prefs.SetString("LastPathToolShape", tool_shape_dir)
    print(f"Set LastPathToolShape to: {tool_shape_dir}")

if not prefs.GetString("DefaultFilePath"):
    prefs.SetString("DefaultFilePath", freecad_dir)
    print(f"Set DefaultFilePath to: {freecad_dir}")

if not prefs.GetString("LastFileToolLibrary"):
    prefs.SetString("LastFileToolLibrary", default_tool_lib_file)
    print(f"Set LastFileToolLibrary to: {default_tool_lib_file}")

# Set new parameters for FreeCAD 1.1+
if major >= 1 and minor >= 1:
    tools_prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/CAM/Tools")

    # Set the BASE path (non-versioned) - FreeCAD will automatically resolve via mostRecentConfigFromBase
    camassets_base = os.path.join(freecad_dir, "CAMAssets")
    if not tools_prefs.GetString("ToolPath"):
        tools_prefs.SetString("ToolPath", camassets_base)
        print(f"Set ToolPath (base) to: {camassets_base}")
        print(f"  → Resolves to: {freecad_assets_dir}")

    if not tools_prefs.GetString("LastToolLibrary"):
        tools_prefs.SetString("LastToolLibrary", "toolbitlibrary://NibblerBOT")
        print(f"Set LastToolLibrary to: toolbitlibrary://NibblerBOT")

    if not tools_prefs.GetString("LastToolLibrarySortKey"):
        tools_prefs.SetString("LastToolLibrarySortKey", "tool_no")
        print(f"Set LastToolLibrarySortKey to: tool_no")

    # Prevent FreeCAD's CAM workbench from offering to migrate CAMAssets
    # We handle migration ourselves using mostRecentConfigFromBase
    migration_prefs = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/CAM/Migration"
    )
    offered_versions = migration_prefs.GetString("OfferedToMigrateCAMAssets", "")

    if offered_versions:
        # Check if current version is already in the list
        version_list = [v.strip() for v in offered_versions.split(",")]
        if version_string not in version_list:
            version_list.append(version_string)
            new_versions = ",".join(version_list)
            migration_prefs.SetString("OfferedToMigrateCAMAssets", new_versions)
            print(
                f"Added {version_string} to OfferedToMigrateCAMAssets: {new_versions}"
            )
    else:
        # First time setting it
        migration_prefs.SetString("OfferedToMigrateCAMAssets", version_string)
        print(f"Set OfferedToMigrateCAMAssets to: {version_string}")


# Set PostProcessor preferences
post_processor_blacklist = [
    "KineticNCBeamicon2",
    "centroid",
    "comparams",
    "dynapath",
    "estlcam",
    "fablin",
    "fangling",
    "fanuc",
    "generic",
    "heidenhain",
    "jtech",
    "mach3_mach4",
    "marlin",
    "nccad",
    "opensbp",
    "philips",
    "refactored_centroid",
    "refactored_grbl",
    "refactored_linuxcnc",
    "refactored_mach3_mach4",
    "refactored_test",
    "rml",
    "rrf",
    "smoothie",
    "uccnc",
    "wedm",
]
if not prefs.GetString("PostProcessorBlacklist"):
    prefs.SetString("PostProcessorBlacklist", str(post_processor_blacklist))
    print(f"Set PostProcessorBlacklist to: {post_processor_blacklist}")

post_processor_output_file = os.path.join(gcode_dir, "%d.ngc")
if not prefs.GetString("PostProcessorOutputFile"):
    prefs.SetString("PostProcessorOutputFile", post_processor_output_file)
    print(f"Set PostProcessorOutputFile to: {post_processor_output_file}")

lib_area_curve_accuracy = 0.010160000000
if not prefs.GetFloat("LibAreaCurveAccuracy"):
    prefs.SetFloat("LibAreaCurveAccuracy", lib_area_curve_accuracy)
    print(f"Set LibAreaCurveAccuracy to: {lib_area_curve_accuracy}")

geometry_tolerance = 0.010160000000
if not prefs.GetFloat("GeometryTolerance"):
    prefs.SetFloat("GeometryTolerance", geometry_tolerance)
    print(f"Set GeometryTolerance to: {geometry_tolerance}")

post_processor_default = "NibblerBOT"
if not prefs.GetString("PostProcessorDefault"):
    prefs.SetString("PostProcessorDefault", post_processor_default)
    print(f"Set PostProcessorDefault to: {post_processor_default}")


if (
    not prefs.GetString("EnableAdvancedOCLFeatures")
    or prefs.GetString("EnableAdvancedOCLFeatures") == "False"
):
    prefs.SetString("EnableAdvancedOCLFeatures", "True")
    print(f"Set EnableAdvancedOCLFeatures to: True")

if (
    not prefs.GetString("EnableExperimentalFeatures")
    or prefs.GetString("EnableExperimentalFeatures") == "False"
):
    prefs.SetString("EnableExperimentalFeatures", "True")
    print(f"Set EnableExperimentalFeatures to: True")

# Copy all files from source directories to target directories
source_dir = os.path.dirname(__file__)  # Directory containing this script
source_subdirs = {
    os.path.join(source_tools_base, "Bit"): tool_bit_dir,
    os.path.join(source_tools_base, "Library"): tool_lib_dir,
    os.path.join(source_tools_base, "Shape"): tool_shape_dir,
    "PostProcessor": os.path.join(FreeCAD.getUserAppDataDir(), "Macro"),
    "Jobs": freecad_dir,
    "Classes/FreeCAD CAM 101 - Intro to CAM/Lesson 1": lesson1_dir,
    "Classes/FreeCAD CAM 101 - Intro to CAM/Lesson 2": lesson2_dir,
    "Classes/FreeCAD CAM 101 - Intro to CAM/Lesson 3": lesson3_dir,
}

manifest_path = os.path.join(freecad_dir, ".nibbler_manifest.json")


def load_manifest():
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def sync_group(source_path, target_path, group_name, file_filter=None):
    manifest = load_manifest()
    managed_files = set(manifest.get(group_name, []))
    source_files = set(
        f
        for f in os.listdir(source_path)
        if os.path.isfile(os.path.join(source_path, f))
        and (file_filter(f) if file_filter else True)
    )

    # Remove files that were managed but no longer exist in source
    for filename in managed_files - source_files:
        target_file = os.path.join(target_path, filename)
        if os.path.exists(target_file):
            os.remove(target_file)
            print(f"Removed {filename} from {target_path}")

    # Copy new/updated files from source
    for filename in source_files:
        src_file = os.path.join(source_path, filename)
        dst_file = os.path.join(target_path, filename)
        shutil.copy(src_file, dst_file)
        print(f"Copied {filename} to {target_path}")

    # Update manifest
    manifest[group_name] = list(source_files)
    save_manifest(manifest)


# Sync tool, class, and job directories
for subdir, destination in source_subdirs.items():
    source_path = os.path.join(source_dir, subdir)
    if os.path.exists(source_path):
        if subdir == "Jobs":

            def job_file_filter(filename):
                return filename.startswith("job_") and filename.endswith(".json")

            sync_group(source_path, destination, subdir, file_filter=job_file_filter)
        else:
            sync_group(source_path, destination, subdir)
    else:
        print(f"Source directory not found: {source_path}. Skipping.")

print("Installation complete!")
