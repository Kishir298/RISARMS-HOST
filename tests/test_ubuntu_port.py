"""Behavior checks for the additive Ubuntu candidate, without root mutations."""
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from risarms_host import ubuntu_release

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'deployment/ubuntu' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ubuntu_metadata_preserves_input_and_client_targets():
    original = json.loads((ROOT / 'compatibility.json').read_text())
    snapshot = json.loads(json.dumps(original))
    candidate = ubuntu_release.manifest_for_ubuntu(original)
    assert original == snapshot
    assert candidate['server_deployment']['distribution'] == 'ubuntu'
    assert candidate['server_deployment']['init'] == 'systemd'
    assert candidate['release_channel'] == 'beta'
    expected = [e for e in original['supported_operating_systems'] if e.get('role') != 'server']
    assert candidate['supported_operating_systems'][:-1] == expected


def test_config_reconcile_preserves_secret(tmp_path):
    config = load_script('configure')
    base, data = tmp_path / 'etc', tmp_path / 'data'
    config.configure(base, data, 'https://core.local')
    secret = (base / 'rescs.env').read_bytes()
    config.reconcile(base, data, 'https://portal.example.test')
    assert (base / 'rescs.env').read_bytes() == secret
    assert json.loads((data / 'core/gateway.json').read_text())['public_origin'] == 'https://portal.example.test'
    with pytest.raises(SystemExit, match='Refusing to overwrite'):
        config.configure(base, data, 'https://core.local')


def archive(tmp_path, name, kind=None):
    path = tmp_path / 'backup.tar.gz'
    with tarfile.open(path, 'w:gz') as tar:
        member = tarfile.TarInfo(name)
        if kind:
            member.type = kind
            member.linkname = '/etc/passwd'
            tar.addfile(member)
        else:
            member.size = 2
            tar.addfile(member, io.BytesIO(b'ok'))
    return path


def test_backup_accepts_expected_file(tmp_path):
    load_script('validate-backup').validate(archive(tmp_path, 'var/lib/risarms/core/test.json'))


@pytest.mark.parametrize('name,kind', [
    ('../etc/passwd', None), ('/etc/passwd', None), ('etc/passwd', None),
    ('var/lib/risarms/core/link', tarfile.SYMTYPE),
    ('var/lib/risarms/core/link', tarfile.LNKTYPE),
    ('var/lib/risarms/core/device', tarfile.CHRTYPE),
])
def test_backup_rejects_unsafe_members(tmp_path, name, kind):
    with pytest.raises(ValueError):
        load_script('validate-backup').validate(archive(tmp_path, name, kind))


def test_backup_accepts_caddyfile(tmp_path):
    load_script('validate-backup').validate(archive(tmp_path, 'etc/caddy/Caddyfile'))


def test_ubuntu_file_inventory_matches_manifest():
    expected = {
        'README.md', 'backup.sh', 'configure.py', 'doctor.sh', 'install.sh',
        'lib.sh', 'portal.caddy', 'restore.sh', 'risarms-core.service',
        'risarms-rescs.service', 'rollback.sh', 'upgrade.sh', 'validate-backup.py',
    }
    actual = {path.name for path in (ROOT / 'deployment/ubuntu').iterdir() if path.is_file()}
    assert actual == expected
    for relative in (
        'risarms_host/ubuntu_release.py',
        '.github/workflows/ubuntu-candidate.yml',
        'tests/test_ubuntu_port.py',
        'UBUNTU-PORT-FILES.md',
    ):
        assert (ROOT / relative).is_file(), relative


def test_ubuntu_shell_scripts_are_executable_in_git():
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-s', 'deployment/ubuntu/*.sh'],
        capture_output=True, text=True, check=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, 'no Ubuntu shell scripts are tracked'
    for line in lines:
        assert line.split()[0] == '100755', line


def test_ubuntu_files_use_lf_endings():
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z', '--', 'deployment/ubuntu'],
        capture_output=True, check=True,
    )
    for raw in result.stdout.split(b'\0'):
        if not raw:
            continue
        path = ROOT / raw.decode('utf-8')
        if path.is_file():
            assert b'\r' not in path.read_bytes(), path


def test_python310_tomllib_fallback(tmp_path, monkeypatch):
    from risarms_host.ubuntu_release import _project_version

    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding='utf-8')
    monkeypatch.setitem(sys.modules, 'tomllib', None)
    assert _project_version(pyproject) == '1.2.3'


def test_same_version_upgrade_is_refused():
    text = (ROOT / 'deployment/ubuntu/upgrade.sh').read_text(encoding='utf-8')
    assert 'same-version upgrade is refused' in text
    assert 'reinstalling through the installer' not in text
    assert 'risarms_die' in text


def test_install_sh_guards_candidate_paths():
    text = (ROOT / 'deployment/ubuntu/install.sh').read_text(encoding='utf-8')
    assert 'systemd-analyze' not in text
    assert 'RISARMS_APP == /opt/risarms' in text
    assert 'RISARMS_ETC == /etc/risarms' in text
    assert 'RISARMS_DATA == /var/lib/risarms' in text
    assert 'install -d -m 0711 -o root -g root "$RISARMS_DATA"' in text
    assert 'chmod 0600 "$RISARMS_ETC"/*.env' in text


def test_systemd_units_apply_hardening():
    core = (ROOT / 'deployment/ubuntu/risarms-core.service').read_text(encoding='utf-8')
    rescs = (ROOT / 'deployment/ubuntu/risarms-rescs.service').read_text(encoding='utf-8')
    for unit in (core, rescs):
        assert 'NoNewPrivileges=true' in unit
        assert 'ProtectHome=true' in unit
        assert 'ProtectSystem=strict' in unit
        assert 'UMask=0077' in unit
    assert 'ReadWritePaths=/var/lib/risarms/core' in core
    assert 'ReadWritePaths=/var/lib/risarms/rescs' in rescs


def test_workflow_checks_candidate_assets():
    text = (ROOT / '.github/workflows/ubuntu-candidate.yml').read_text(encoding='utf-8')
    for needle in (
        'ruff', 'bash -n', '100755', 'deployment/ubuntu/install.sh',
        'ubuntu-provenance.json', 'python-version',
        'TIVISS-CLIENT/pyproject.toml',
    ):
        assert needle in text, needle


def test_release_archive_has_ubuntu_instructions_and_pins(tmp_path, monkeypatch):
    import hashlib
    import shutil

    from risarms_host import revisions

    def fake_stage(root, destination, lock):
        destination.mkdir(parents=True)
        shutil.copytree(ROOT / 'deployment/ubuntu', destination / 'deployment/ubuntu')
        for component in ('CORE-HOST', 'CORE-CLIENT'):
            target = destination / component
            target.mkdir()
            (target / 'pyproject.toml').write_text('[project]\nversion="0.6.0"\n')
        return destination

    monkeypatch.setattr(revisions, 'stage', fake_stage)
    archive_path = ubuntu_release.build(ROOT, tmp_path / 'out')
    with tarfile.open(archive_path) as tar:
        prefix = archive_path.name.removesuffix('.tar.gz')
        manifest = json.load(tar.extractfile(f'{prefix}/compatibility.json'))
        lock = json.load(tar.extractfile(f'{prefix}/components.lock.json'))
        instructions = tar.extractfile(f'{prefix}/INSTALL.txt').read().decode()
    assert manifest['server_deployment']['distribution'] == 'ubuntu'
    assert lock['target'] == 'ubuntu-24.04-x86_64-glibc-systemd'
    assert 'deployment/ubuntu/install.sh' in instructions
    provenance = json.loads((archive_path.parent / 'ubuntu-provenance.json').read_text())
    assert provenance['sha256'] == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert provenance['components'] == lock['components']
