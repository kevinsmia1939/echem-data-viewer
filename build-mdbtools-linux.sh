#!/usr/bin/env bash
# Maintainer script: rebuild the bundled static Linux x86_64 mdb-export.
set -euo pipefail

viewer_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(uname -m)" != x86_64 ]]; then
    echo "This script builds the Linux x86_64 bundle only." >&2
    exit 1
fi
if [[ ! -f "$viewer_dir/mdbtools/configure.ac" ]]; then
    echo "Initialize the mdbtools submodule first: git submodule update --init mdbtools" >&2
    exit 1
fi
mkdir -p "$viewer_dir/vendor/mdbtools/linux-x86_64"
podman run --rm \
    -v "$viewer_dir/mdbtools:/source:ro" \
    -v "$viewer_dir/vendor/mdbtools/linux-x86_64:/output" \
    alpine:3.20 sh -c '
set -eu
apk add --no-cache build-base autoconf automake libtool pkgconf gettext-dev
cp -a /source /tmp/mdbtools
cd /tmp/mdbtools
autoreconf -fi
./configure --disable-glib --disable-shared --enable-static --disable-man
make -j2 LDFLAGS=-all-static
cp src/util/mdb-export /output/mdb-export
chmod 755 /output/mdb-export
/output/mdb-export --version
'
