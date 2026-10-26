# Builds dist\VrikshaDesk (the program) and THIRD_PARTY_LICENSES.txt.
# Needs: pip install -r requirements.txt -r requirements-build.txt
# Native tools log to stderr; failures are caught through $LASTEXITCODE instead.
Set-Location (Split-Path $PSScriptRoot -Parent)

# Licence texts of everything we ship (not the build tools).
$tools = "pyinstaller", "pyinstaller-hooks-contrib", "pip-licenses", "prettytable", "wcwidth", "altgraph", "pefile", "packaging", "setuptools", "pip", "tomli"
Get-Content packaging\NOTICE.txt | Set-Content THIRD_PARTY_LICENSES.txt -Encoding utf8
"`n`n==================== LICENCE TEXTS ====================`n" | Add-Content THIRD_PARTY_LICENSES.txt -Encoding utf8
pip-licenses --from=mixed --format=plain-vertical --with-license-file --no-license-path --ignore-packages @tools |
    Add-Content THIRD_PARTY_LICENSES.txt -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "pip-licenses failed" }

# keyring finds its Windows backend through package metadata, which PyInstaller
# cannot see on its own.
pyinstaller --noconfirm --clean --windowed --name VrikshaDesk `
    --collect-submodules keyring.backends --copy-metadata keyring main.py
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }
