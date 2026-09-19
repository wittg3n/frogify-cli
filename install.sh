#!/bin/sh
# Install a verified GitHub Release without Python or administrator access.
set -eu

die() {
    printf '%s\n' "error: $*" >&2
    exit 1
}

main() {
    os=$(uname -s)
    [ "$os" = Linux ] || die "Unsupported operating system: $os"
    machine=$(uname -m)
    case "$machine" in
        x86_64|amd64) arch=x86_64 ;;
        *) die "Frogify currently provides a standalone Linux binary for x86_64 only.
Detected architecture: $machine" ;;
    esac
    command -v curl >/dev/null 2>&1 || die "curl is required to install Frogify."
    if command -v sha256sum >/dev/null 2>&1; then
        checksum=sha256sum
    elif command -v shasum >/dev/null 2>&1; then
        checksum=shasum
    else
        die "No SHA-256 verification tool was found (sha256sum or shasum)."
    fi

    repository=https://github.com/wittg3n/frogify-cli
    version=${FROGIFY_VERSION:-}
    if [ -z "$version" ]; then
        latest=$(curl --fail --silent --show-error --location --proto '=https' \
            --proto-redir '=https' --output /dev/null --write-out '%{url_effective}' \
            "$repository/releases/latest") || die "Unable to resolve the latest Frogify release."
        case "$latest" in
            "$repository/releases/tag/"*) version=${latest##*/} ;;
            *) die "Unexpected latest release URL: $latest" ;;
        esac
    fi
    version=${version#v}
    case "$version" in
        ''|[!0-9]*|*[!0-9A-Za-z.+-]*) die "Invalid Frogify version: $version" ;;
    esac
    version=v$version
    install_dir=${FROGIFY_INSTALL_DIR:-${HOME:?HOME must be set}/.local/bin}
    # Make paths absolute so leading dashes and relative paths are unambiguous.
    case "$install_dir" in /*) ;; *) install_dir=$PWD/$install_dir ;; esac
    archive=frogify-linux-$arch.tar.gz
    url=$repository/releases/download/$version
    work=$(mktemp -d) || die "Unable to create a temporary directory."
    stage=
    trap 'rm -rf -- "$work"; if [ -n "$stage" ]; then rm -rf -- "$stage"; fi' 0
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP

    printf 'Frogify %s\nPlatform: linux-%s\nInstalling to %s/frogify\n' \
        "$version" "$arch" "$install_dir"
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        "$url/$archive" --output "$work/$archive" || die "Unable to download Frogify $version."
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        "$url/$archive.sha256" --output "$work/checksum" || die "Unable to download the checksum."
    read -r expected filename extra < "$work/checksum" || die "Invalid checksum file."
    [ "${#expected}" -eq 64 ] && [ "$filename" = "$archive" ] && [ -z "$extra" ] \
        || die "Invalid checksum file."
    case "$expected" in *[!0-9a-f]*) die "Invalid SHA-256 checksum." ;; esac
    if [ "$checksum" = sha256sum ]; then
        actual=$(sha256sum < "$work/$archive") || die "Unable to calculate SHA-256."
    else
        actual=$(shasum -a 256 < "$work/$archive") || die "Unable to calculate SHA-256."
    fi
    [ "${actual%% *}" = "$expected" ] || die "Checksum verification failed."
    printf '%s\n' 'Checksum verified.'

    members=$(tar -tzf "$work/$archive") || die "Unable to read the release archive."
    seen_binary=0
    while IFS= read -r member; do
        case "$member" in
            /*|../*|*/../*|*/..|*\\*) die "Unsafe release archive member: $member" ;;
            frogify)
                [ "$seen_binary" = 0 ] || die "Duplicate release binary."
                seen_binary=1 ;;
            THIRD_PARTY_NOTICES.md|inventory.json|licenses/*|sources/*) ;;
            *) die "Unexpected release archive member: $member" ;;
        esac
    done <<EOF
$members
EOF
    [ "$seen_binary" = 1 ] || die "Release archive is missing frogify at its root."
    # Extract to stdout: archive paths, permissions and links cannot escape our directory.
    tar -xOzf "$work/$archive" frogify > "$work/frogify" \
        || die "Unable to extract Frogify."
    [ -s "$work/frogify" ] || die "The release binary is empty."
    mkdir -p "$install_dir" || die "Unable to create installation directory: $install_dir"
    [ ! -d "$install_dir/frogify" ] || die "The destination is a directory: $install_dir/frogify"
    stage=$(mktemp -d "$install_dir/.frogify-install.XXXXXX") \
        || die "Unable to stage Frogify in $install_dir."
    cp "$work/frogify" "$stage/frogify" || die "Unable to stage the new binary."
    chmod 755 "$stage/frogify" || die "Unable to set executable permissions."
    mv -f "$stage/frogify" "$install_dir/frogify" || die "Unable to replace Frogify."
    printf 'Frogify installed successfully:\n  %s/frogify\n' "$install_dir"
    case ":${PATH:-}:" in
        *":$install_dir:"*) printf 'Run:\n  frogify --version\n  frogify doctor\n' ;;
        *) printf 'Add this directory to your PATH:\n  %s\nThen run frogify doctor.\n' "$install_dir" ;;
    esac
}

main
