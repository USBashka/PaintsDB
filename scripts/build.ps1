param([string]$Python = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -m pytest -q --basetemp=.build-tests
if ($LASTEXITCODE -ne 0) { throw 'Проверки завершились с ошибкой' }
& $Python -m PyInstaller --noconfirm PaintsDB.spec
if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать EXE' }
Get-FileHash -Algorithm SHA256 -LiteralPath 'dist\PaintsDB.exe'
