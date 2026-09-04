# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import shutil
import tkinter
import zipfile


project_root = Path(SPEC).resolve().parents[2]


def _collect_zipfs_tk_data():
    """Expand Python 3.14's zipfs Tcl/Tk libraries for PyInstaller.

    Python 3.14 ships the Tcl/Tk scripts in libtcl*.zip/libtk*.zip instead
    of ordinary tclX.Y/tkX.Y directories.  PyInstaller's tkinter runtime
    hook expects ordinary _tcl_data/_tk_data directories, so include the
    archive contents with their top-level library directory stripped.
    """

    python_root = Path(tkinter.__file__).resolve().parents[2]
    tcl_root = python_root / "tcl"
    tcl_archive = next(iter(sorted(tcl_root.glob("libtcl*.zip"))), None)
    tk_archive = next(iter(sorted(tcl_root.glob("libtk*.zip"))), None)
    if not tcl_archive or not tk_archive:
        return []

    staging_root = project_root / "build" / "packaging_tcl_data"
    if staging_root.exists():
        shutil.rmtree(staging_root)

    data_files = []
    for archive, top_level, destination in (
        (tcl_archive, "tcl_library", "_tcl_data"),
        (tk_archive, "tk_library", "_tk_data"),
    ):
        destination_root = staging_root / destination
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                member_name = member.filename.replace("\\", "/")
                if member.is_dir() or not member_name.startswith(top_level + "/"):
                    continue
                relative = Path(member_name[len(top_level) + 1 :])
                output = destination_root / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)
                data_files.append((str(output), str(Path(destination) / relative.parent)))
    return data_files


tk_data = _collect_zipfs_tk_data()
app_icon_png = project_root / "assets" / "icon.png"
app_icon_ico = project_root / "assets" / "icon.ico"

a = Analysis(
    [str(project_root / "run_configurator.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=tk_data + [
        (str(app_icon_png), "assets"),
        (str(app_icon_ico), "assets"),
    ],
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "serial.tools.list_ports_windows",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PicoController2MNK",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(app_icon_ico),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PicoController2MNK",
)
