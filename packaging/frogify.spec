from pathlib import Path
import os
import runpy

root = Path(SPECPATH).parent
rapidfuzz_native = [
    "rapidfuzz." + name
    for name in (
        "_feature_detector_cpp", "fuzz_cpp", "fuzz_cpp_avx2", "process_cpp_impl", "utils_cpp",
        "distance._initialize_cpp", "distance.metrics_cpp", "distance.metrics_cpp_avx2",
    )
]

# Application imports are static. Local hooks retain RapidFuzz's Python backend
# and the Pygments features used by Rich; the standard certifi hook retains CAs.
a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[str(root / "packaging" / "hooks")],
    runtime_hooks=[str(root / "packaging/hooks/rthook-rapidfuzz.py")],
    # Only optional CPython REPL/history imports use readline. Typer uses input().
    excludes=["readline", "bz2", "_bz2", "lzma", "_lzma", *rapidfuzz_native],
    noarchive=False,
    optimize=0,
)
notices = Path(os.environ.get("FROGIFY_DIST_DIR", "dist")) / "linux"
runpy.run_path(str(root / "packaging" / "notices.py"))["collect"](
    root, notices, a.pure, a.binaries
)
# Compliance evidence travels beside the executable; it is not runtime data.
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="frogify",
    debug=False,
    strip=True,
    upx=False,
    console=True,
)
runpy.run_path(str(root / "packaging" / "notices.py"))["finalize_binary"](
    notices, Path(exe.name), stripped=True
)
