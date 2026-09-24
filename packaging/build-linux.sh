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
# Build verified runtime wheels outside the environment analyzed by PyInstaller.
uv export --locked --no-dev --group binary-build --prune ninja --prune scikit-build-core \
    --no-emit-project --format requirements-txt --output-file /tmp/frogify-freeze-requirements.txt
python -m pip wheel --require-hashes --no-build-isolation \
    -r /tmp/frogify-freeze-requirements.txt --wheel-dir /tmp/frogify-wheels
uv venv --python "$(command -v python)" /tmp/frogify-freeze
uv pip install --python /tmp/frogify-freeze/bin/python --no-index /tmp/frogify-wheels/*.whl
output=${FROGIFY_DIST_DIR:-dist}
/tmp/frogify-freeze/bin/python -m PyInstaller --clean --noconfirm --distpath "$output/linux" \
    --workpath build/pyinstaller packaging/frogify.spec
/tmp/frogify-freeze/bin/python packaging/release_set.py build "$output/linux" \
    --output "$output/binary"
