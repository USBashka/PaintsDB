"""Package the built standalone EXE, synthetic data, docs and dependency notices."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tomllib

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
executable = root / "dist/PaintsDB.exe"
if not executable.is_file():
    raise SystemExit("Сначала выполните scripts/build.ps1")

payload = [(executable, "PaintsDB.exe")]
for name in ("README.md", "THIRD_PARTY_NOTICES.md"):
    payload.append((root / name, name))
for folder in ("docs", "licenses", "skills"):
    payload.extend((path, path.relative_to(root).as_posix())
                   for path in sorted((root / folder).rglob("*"))
                   if path.is_file() and path.suffix not in {".pyc", ".pyo"})
payload.append((root / "demo/Демонстрация.paintsdb", "demo/Демонстрация.paintsdb"))

archive = root / f"dist/PaintsDB-{version}-win-x64.zip"
with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
    for path, name in payload:
        bundle.write(path, name)
with ZipFile(archive) as bundle:
    broken = bundle.testzip()
    if broken:
        raise SystemExit(f"Неверная контрольная сумма в архиве: {broken}")

lines = [f"{sha256(path.read_bytes()).hexdigest()}  {path.name}"
         for path in (executable, archive)]
(root / "dist/SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="ascii")
print(archive)
print("\n".join(lines))
