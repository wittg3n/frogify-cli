#!/bin/sh
# Only release data and this test script are mounted in clean runtime containers.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' 0
trap 'exit 130' INT
trap 'exit 143' TERM
export HOME=$work/home
export XDG_CONFIG_HOME=$HOME/.config
export XDG_DATA_HOME=$HOME/.local/share
export XDG_STATE_HOME=$HOME/.local/state
export NO_COLOR=1
export COLUMNS=160
mkdir -p "$HOME"
cd /artifacts
sha256sum -c frogify-linux-x86_64.tar.gz.sha256
tar -tzf frogify-linux-x86_64.tar.gz > "$work/members"
for member in frogify THIRD_PARTY_NOTICES.md inventory.json licenses/; do
    grep -qx "$member" "$work/members"
done
if grep -q '^sources/' "$work/members"; then
    echo 'Source archives must travel in the paired source asset.' >&2
    exit 1
fi
tar -xzf frogify-linux-x86_64.tar.gz -C "$work"
cd "$work"
[ "$(./frogify --version)" = "frogify $FROGIFY_EXPECTED_VERSION" ]
./frogify --help
# Missing external tools/providers legitimately return 1. Require the full
# diagnostic table and successful bundled-module/config/database checks.
status=0
./frogify doctor > doctor.txt 2>&1 || status=$?
cat doctor.txt
[ "$status" -le 1 ]
grep -q 'Frogify doctor' doctor.txt
for component in requests mutagen Config Database; do
    grep -Eq "$component[[:space:]]+.*OK" doctor.txt
done
if grep -Eq 'Traceback|ModuleNotFoundError|ImportError|Error:' doctor.txt; then
    exit 1
fi
