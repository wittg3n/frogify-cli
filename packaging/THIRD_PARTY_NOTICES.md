# Standalone distribution notices

Frogify's own source remains MIT licensed; see `licenses/frogify/0-LICENSE`.
The executable contains third-party Python modules, CPython, a PyInstaller
bootloader, and native libraries. It is not an MIT-only distribution.

`inventory.json` is generated from the actual PyInstaller Analysis tables and
installed distribution/RPM metadata. It records versions, declared licenses,
bundled native files, copied license texts, and missing materials. It deliberately
does not substitute an entire RPM's license declaration for a reviewed conclusion
about a particular shared library. Build-machine paths are not included.

Package license texts are under `licenses/`. The unmodified Mutagen and certifi source
archives are supplied under `sources/`, verified against the source hashes in `uv.lock`.
Keep these materials with any copy of this candidate. Sources are provided directly;
this document is not a written source offer.

## Publication blocker

The standalone candidate must not be published yet. Review the distribution terms
for the combined executable containing Mutagen (GPL-2.0-or-later) and GNU readline
(GPL-3.0-or-later). Verify complete corresponding source and build/install materials
for all applicable GPL/LGPL components, including the exact native-library builds.
Merely linking upstream homepages or shipping Frogify's sdist is not a substitute
for those materials. Missing native license texts listed in the generated inventory
must also be supplied. No conclusion that Frogify's own MIT source must be relicensed
is made here.

`python packaging/notices.py --check-release <inventory.json>` fails while these
items remain unresolved. CI invokes it before release uploads and PyPI publication.
Resolve the concrete materials and distribution terms through a reviewed patch;
do not bypass the check with an environment flag.

## Authoritative references

- [Mutagen license and source](https://github.com/quodlibet/mutagen/blob/main/COPYING)
- [GPL version 2, section 3](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
- [GPL version 3, sections 5 and 6](https://www.gnu.org/licenses/gpl-3.0.html)
- [PyInstaller license and bootloader exception](https://pyinstaller.org/en/stable/license.html)
- [Official manylinux build sources](https://github.com/pypa/manylinux)

PyInstaller's exception does not waive dependency license obligations. FFmpeg,
ffprobe and aria2 are external executables and are not part of this archive.
