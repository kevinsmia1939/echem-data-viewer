#!/bin/bash
set -eu
viewer_dir="/home/kevin/Dropbox/Desktop/software/nox-viewer"
applications_dir="/home/kevin/.local/share/applications"
mime_dir="/home/kevin/.local/share/mime"
mkdir -p "$applications_dir" "$mime_dir/packages"
desktop-file-validate "$viewer_dir/org.kevin.NoxViewer.desktop"
install -m 644 "$viewer_dir/org.kevin.NoxViewer.desktop" "$applications_dir/org.kevin.NoxViewer.desktop"
install -m 644 "$viewer_dir/metrohm-nova-nox.xml" "$mime_dir/packages/metrohm-nova-nox.xml"
update-mime-database "$mime_dir"
update-desktop-database "$applications_dir"
xdg-mime default org.kevin.NoxViewer.desktop application/x-metrohm-nova-nox
xdg-mime default org.kevin.NoxViewer.desktop application/x-biologic-mpr
xdg-mime default org.kevin.NoxViewer.desktop application/x-biologic-mpt
echo "Installed Electrochemistry Data Viewer; default for .nox, .mpr and .mpt files."
