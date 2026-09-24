# Standalone distribution notices

Frogify's own source remains MIT licensed. The executable contains third-party
components under their own terms. Exact versions, license origins, source hashes,
native ownership and obligations are recorded in `inventory.json`. Keep this
document, the inventory and `licenses/` with the executable when redistributing it.

## Corresponding source

The binary installation archive and its complete corresponding-source archive
are paired assets on the same versioned release:

- [v0.2.0 release](https://github.com/wittg3n/frogify-cli/releases/tag/v0.2.0)
- [Corresponding source](https://github.com/wittg3n/frogify-cli/releases/download/v0.2.0/frogify-linux-x86_64-sources.tar.gz)

These describe the required publication location for this prepared candidate;
building the candidate does not publish that release. The release workflow keeps
the release in draft until both assets and their checksums have been uploaded and
verified. Both must remain available together, with equivalent free download
access. Recipients do not have to download the source to install the executable.
Redistributors must preserve equivalent source access, not merely copy this URL
without providing the required materials.

Mutagen is GPL-2.0-or-later. This combined standalone distribution uses the later
GPLv3 terms permitted by that grant; both its original COPYING and the GPLv3 text
are supplied. GPLv3 section 6(d) permits equivalent network access to corresponding
source without requiring recipients to download it. GPLv2 section 3 also describes
equivalent source access at the same designated place. certifi's MPL-2.0 section
3.2 requires source availability and directions for obtaining it. The paired source
asset supplies those materials directly; this is not a written source offer.

The current presence of Mutagen drives a conservative complete-source policy for
the combined executable. This is recomputed from the actual component inventory;
it is not a leftover readline requirement. Individually permissive components are
not marked as independently requiring source. Their sources are supplied as part
of the combined distribution's complete source and build materials.

## Retained components

- Mutagen inspects audio in memory. Its locked source archive is compared with
  installed Python sources before collection succeeds.
- RapidFuzz's supported Python implementation preserves the existing matching
  algorithms. Native RapidFuzz extensions and GCC runtimes are not bundled.
- CPython includes its license and embedded notices, including Expat, libmpdec
  and hashing code. The source asset includes its source and image build recipes.
- PyInstaller's bootloader license and exception are included. The exception
  does not waive obligations for unrelated components.
- OpenSSL 3.5.8 uses Apache-2.0. Its source LICENSE and AUTHORS are included.
  SQLite retains its upstream public-domain disclaimer. Other native and Python
  package terms are recorded individually, without deriving licenses from names.
- Readline, setuptools, bzip2 and XZ/liblzma are absent from the frozen runtime.

The normal installer downloads only the binary archive and checksum. It saves
notices and licenses under `${XDG_DATA_HOME:-$HOME/.local/share}/frogify/0.2.0/`,
independently of a custom executable installation directory.

## Verification

`python packaging/notices.py --check-release dist/linux/inventory.json` validates
the complete staging tree. `python packaging/release_set.py check dist/binary`
validates both distribution assets, their checksums, identical inventories,
version and every required evidence file. Readiness is computed from blockers;
neither this document nor the release manifest overrides a failed check.

FFmpeg, ffprobe and aria2c remain external tools and are not included.
