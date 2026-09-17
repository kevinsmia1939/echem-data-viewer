#!/usr/bin/env bash
set -euo pipefail

viewer_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
applications_dir="$data_dir/applications"
mime_dir="$data_dir/mime"
venv_dir="$viewer_dir/.venv"

if [[ ! -f "$viewer_dir/galvani/galvani/Nova.py" ]]; then
    if [[ ! -d "$viewer_dir/.git" ]]; then
        echo "Galvani submodule missing. Clone with: git clone --recurse-submodules https://github.com/kevinsmia1939/echem-data-viewer.git" >&2
        exit 1
    fi
    git -C "$viewer_dir" submodule update --init --recursive
fi

python3 -m venv --system-site-packages "$venv_dir"
"$venv_dir/bin/python" -m pip install -r "$viewer_dir/requirements.txt"

mkdir -p "$applications_dir" "$mime_dir/packages"
"$venv_dir/bin/python" - "$viewer_dir" "$applications_dir" <<'PY'
from pathlib import Path
import sys

viewer_dir, applications_dir = map(Path, sys.argv[1:])
template = (viewer_dir / "org.kevin.NoxViewer.desktop").read_text(encoding="utf-8")

def desktop_quote(path):
    value = str(path)
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return '"' + value + '"'

entry = template.replace("@PYTHON@", desktop_quote(viewer_dir / ".venv/bin/python"))
entry = entry.replace("@APP@", desktop_quote(viewer_dir / "nox_viewer.py"))
(applications_dir / "org.kevin.NoxViewer.desktop").write_text(entry, encoding="utf-8")
PY

desktop-file-validate "$applications_dir/org.kevin.NoxViewer.desktop"
install -m 644 "$viewer_dir/metrohm-nova-nox.xml" "$mime_dir/packages/metrohm-nova-nox.xml"
update-mime-database "$mime_dir"
update-desktop-database "$applications_dir"
xdg-mime default org.kevin.NoxViewer.desktop application/x-metrohm-nova-nox
xdg-mime default org.kevin.NoxViewer.desktop application/x-biologic-mpr
xdg-mime default org.kevin.NoxViewer.desktop application/x-biologic-mpt
echo "Installed Electrochemistry Data Viewer; default for .nox, .mpr and .mpt files."
