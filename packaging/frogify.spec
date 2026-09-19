from pathlib import Path
import os
import runpy

root = Path(SPECPATH).parent

# frogify and mp3juice use static imports. Their dependencies' maintained
# PyInstaller hooks handle rapidfuzz's dynamic native backends and certifi data.
# No application-specific hidden imports are needed.
a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
notices = Path(os.environ.get("FROGIFY_DIST_DIR", "dist")) / "linux"
runpy.run_path(str(root / "packaging" / "notices.py"))["collect"](
    root, notices, a.pure, a.binaries
)
# Keep notices with the installed executable too, even when it is copied alone.
for path in notices.rglob("*"):
    if path.is_file() and path.name != "frogify":
        a.datas.append(("distribution/" + path.relative_to(notices).as_posix(), str(path), "DATA"))
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="frogify",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
