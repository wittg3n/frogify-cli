# Standalone source and build materials

The `frogify-linux-x86_64-sources.tar.gz` asset belongs to the binary asset on the
same v0.2.0 release. Its `inventory.json` must be byte-identical to the binary
archive's inventory. The release-set manifest and individual SHA-256 files bind
the two archives together. Source package versions, origins and checksums are
recorded per component. Shared source archives occur only once.

Unpack this source asset, then unpack `sources/frogify-0.2.0.tar` into an empty
directory. Copy `sources/build-info/` into that directory. The snapshot contains
Frogify's preferred Python sources, LICENSE, README, pyproject.toml and uv.lock.
Build-info supplies packaging scripts, hooks, license materials and installer.

With Docker on an x86_64 Linux host, run:

```sh
docker build -f packaging/Dockerfile -t frogify-linux-builder .
docker run --rm -v "$PWD:/src" frogify-linux-builder
python3 packaging/notices.py --check-release dist/linux/inventory.json
python3 packaging/release_set.py check dist/binary
```

The original pinned manylinux2014 image and glibc 2.17 target remain unchanged.
The Dockerfile records the shared libpython build. Original image build scripts
and CPython configuration are under `manylinux/`. Paths under `/opt` are immutable
container locations, not developer or runner paths.

The build verifies locked inputs while constructing wheels, then installs them
into a separate freeze environment. Ninja and scikit-build-core stay outside
that environment. PyInstaller's own execution dependencies may be installed
there, but negative artifact checks prevent setuptools from entering the runtime.
RapidFuzz uses its supported Python backend in the frozen application.

Python sdists include their build definitions. The exact Mutagen source is
compared byte-for-byte with its installed Python modules. All retained components'
source archives accompany the combined distribution; their individual license
requirements remain separately identified. Source availability uses the network
distribution mechanism explained in THIRD_PARTY_NOTICES.md.

Native source RPMs retain upstream tarballs, distributor patches and `.spec`
build/install instructions. Rebuild them using the corresponding CentOS 7 build
environment. Their SHA-256 pins were recorded after `rpm -K` authenticated the
packages with the CentOS signing key in the pinned image. The collector checks
those pins before reading or copying source/license archives.

OpenSSL and SQLite source pins match the official manylinux Dockerfile blob
`b5771fbe1cc255c71d2fa855febe80d4c2c2fa27`; their build recipes come from the pinned
image. CPython's source checksum is the one in the project's Dockerfile.

The retained native inventory is generated anew from Analysis. Removed readline,
GCC runtime, bzip2 and XZ components do not retain stale source-RPM requirements.
Normal system/compiler tools remain build prerequisites.

Both release assets must be provided together. Missing sources, changed hashes,
unknown native inputs, inconsistent versions or missing licenses fail validation.
