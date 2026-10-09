# Build a single Windows .exe (PyInstaller).
# Requires: python -m pip install -r requirements.txt -r requirements-dev.txt
# Run:      pwsh -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm --onefile --windowed --name "MusicTopTracks" `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtWebEngineQuick `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtDesigner `
    --exclude-module tkinter `
    gui.py

Write-Host ""
Write-Host "Done. File: dist\MusicTopTracks.exe"
Write-Host "Put groups.txt, aliases.csv, etc. next to it - they are read from the .exe folder."
