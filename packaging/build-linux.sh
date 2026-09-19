#!/bin/sh
# Run inside the image built from packaging/Dockerfile, with the checkout at /src.
set -eu
[ "$(uname -m)" = x86_64 ]
[ "$(getconf GNU_LIBC_VERSION)" = 'glibc 2.17' ]
python -c 'import platform; assert platform.python_version() == "3.12.14"'
python -c 'import tomllib, frogify; from pathlib import Path; assert frogify.__version__ == tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]'
# RapidFuzz has no glibc 2.17 wheel at the locked version. Install its locked
# build backend first so source builds cannot resolve unpinned build tools.
export CMAKE_BUILD_PARALLEL_LEVEL=2
uv export --locked --only-group binary-build --no-emit-project \
    --format requirements-txt --output-file /tmp/frogify-build-requirements.txt
python -m pip install --require-hashes -r /tmp/frogify-build-requirements.txt
uv export --locked --no-dev --group binary-build --no-emit-project \
    --format requirements-txt --output-file /tmp/frogify-requirements.txt
python -m pip install --require-hashes --no-build-isolation -r /tmp/frogify-requirements.txt
output=${FROGIFY_DIST_DIR:-dist}
python -m PyInstaller --clean --noconfirm --distpath "$output/linux" \
    --workpath build/pyinstaller packaging/frogify.spec
mkdir -p "$output/binary"
tar --mtime=@946684800 --mode=755 --owner=0 --group=0 --numeric-owner \
    -C "$output/linux" -cf "$output/binary/frogify-linux-x86_64.tar" \
    frogify THIRD_PARTY_NOTICES.md inventory.json licenses sources
gzip -n -f "$output/binary/frogify-linux-x86_64.tar"
cd "$output/binary"
sha256sum frogify-linux-x86_64.tar.gz > frogify-linux-x86_64.tar.gz.sha256
