# Building CORE

## Prerequisites

- Python 3.10+ (3.12 is used in CI)
- `python -m pip install build pyinstaller`
- Windows: PowerShell 5.1 is sufficient for the wheel commands; Git Bash is
  used by CI for packaging commands but is not required to build wheels.
  Windows is not a supported CORE server release target.

## Python wheels

```bash
python -m build --wheel --sdist CORE-HOST
python -m build --wheel --sdist CORE-CLIENT
```

Artifacts land in `CORE-HOST/dist/` and `CORE-CLIENT/dist/`.

## Standalone executables

```bash
python -m pip install -e CORE-HOST -e CORE-CLIENT
python -m PyInstaller --onefile --name core-host \
  --collect-submodules core --collect-data core \
  --distpath dist/host scripts/standalone_host.py
python -m PyInstaller --onefile --name core-client \
  --collect-submodules client --collect-data client \
  --distpath dist/client scripts/standalone_client.py
```

Each executable must be built on its target operating system and
architecture. Cross-compilation is not supported for the bundled runtime.

## Linux server bundle

```bash
python -m build --wheel CORE-HOST
mkdir -p server
cp CORE-HOST/dist/*.whl server/
cp CORE-HOST/deploy/linux/install-server.sh CORE-HOST/deploy/linux/core.service server/
tar -czf CORE-Server-$(python -c "import tomllib;print(tomllib.load(open('CORE-HOST/pyproject.toml','rb'))['project']['version'])")-linux-x64.tar.gz -C server .
```

## Automated releases

Server releases are owned by this repository. `.github/workflows/release.yml`
stages `CORE-HOST`, `CORE-CLIENT`, `RESCS`, `ASCS`, `ASIS` and `TIVISS-HOST`
from their owning repositories at the commits pinned in `components.lock.json`,
assembles the Void x86_64 server archive, re-assembles it to prove the bytes are
identical, installs it with the shipped Void installer in a
`ghcr.io/void-linux/void-glibc-full` container, and emits `SHA256SUMS`,
`provenance.json` and a CycloneDX SBOM.

A version tag `vX.Y.Z` must match `pyproject.toml`, `risarms_host/__init__.py`,
`compatibility.json` and `components.lock.json`; the workflow fails otherwise.
Workflow-dispatch runs build artifacts without publishing a GitHub Release, and
publishing is always a draft.

The desktop application (including its Windows/macOS/Linux installers) is built
and released separately by `.github/workflows/desktop-release.yml` in
`RISARMS-ui`. This repository does not build desktop artifacts, and the retired
monorepo pipeline (wheels and standalone executables for every desktop
platform) no longer exists.

## Tests

```bash
(cd CORE-HOST && python -m pytest -q)
(cd CORE-CLIENT && python -m pytest -q)
ruff check --select F CORE-HOST/core CORE-CLIENT/client
```
