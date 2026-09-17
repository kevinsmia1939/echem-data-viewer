# Installs the viewer for the current Windows user; no administrator rights needed.
param([switch]$SkipFileAssociations)

$ErrorActionPreference = 'Stop'
$viewerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$galvaniReader = Join-Path $viewerDir 'galvani\galvani\Nova.py'
$venvDir = Join-Path $viewerDir '.venv'
$viewerScript = Join-Path $viewerDir 'nox_viewer.py'

if (-not (Test-Path $galvaniReader)) {
    if (-not (Test-Path (Join-Path $viewerDir '.git'))) {
        throw 'Galvani submodule is missing. Clone with: git clone --recurse-submodules https://github.com/kevinsmia1939/echem-data-viewer.git'
    }
    & git -C $viewerDir submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the Galvani submodule.' }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $venvDir
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv $venvDir
} else {
    throw 'Python 3 is required. Install it from python.org, then rerun this script.'
}
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }

$pythonExe = Join-Path $venvDir 'Scripts\python.exe'
$pythonwExe = Join-Path $venvDir 'Scripts\pythonw.exe'
& $pythonExe -m pip install -r (Join-Path $viewerDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }

$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcutPath = Join-Path $startMenu 'Electrochemistry Data Viewer.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonwExe
$shortcut.Arguments = '"' + $viewerScript + '"'
$shortcut.WorkingDirectory = $viewerDir
$shortcut.IconLocation = $pythonwExe
$shortcut.Description = 'View NOVA NOX and BioLogic MPR/MPT measurements'
$shortcut.Save()

if (-not $SkipFileAssociations) {
    $classes = 'HKCU:\Software\Classes'
    $progId = 'EchemDataViewer.Measurement'
    $programKey = Join-Path $classes $progId
    $commandKey = Join-Path $programKey 'shell\open\command'
    New-Item -Path $commandKey -Force | Out-Null
    Set-Item -Path $programKey -Value 'Electrochemistry measurement'
    $openCommand = '"{0}" "{1}" "%1"' -f $pythonwExe, $viewerScript
    Set-Item -Path $commandKey -Value $openCommand

    foreach ($extension in @('.nox', '.mpr', '.mpt')) {
        $extensionKey = Join-Path $classes $extension
        $openWithKey = Join-Path $extensionKey 'OpenWithProgids'
        New-Item -Path $openWithKey -Force | Out-Null
        New-ItemProperty -Path $openWithKey -Name $progId -PropertyType String -Value '' -Force | Out-Null
        # Windows may retain a protected UserChoice default. Register this as
        # the per-user class default without altering UserChoice or its hash.
        Set-Item -Path $extensionKey -Value $progId
    }
}

Write-Host 'Installed Electrochemistry Data Viewer for this user.'
Write-Host "Start Menu shortcut: $shortcutPath"
if (-not $SkipFileAssociations) {
    Write-Host 'Registered .nox, .mpr and .mpt. If double-click still opens another app, choose this viewer in Windows Settings > Apps > Default apps.'
}
