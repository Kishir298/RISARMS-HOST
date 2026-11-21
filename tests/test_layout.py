from risarms_host.layout import BUNDLE_REQUIREMENTS, WORKSPACE_REPOS


def test_required_workspace_repos():
    required = {component.name for component in WORKSPACE_REPOS if component.required}
    assert required == {"core-host", "core-client", "risarms-ui", "rescs", "tiviss-host"}


def test_component_marker_file_detection(tmp_path):
    component = WORKSPACE_REPOS[0]
    (tmp_path / component.path).mkdir()
    assert not component.check(tmp_path)
    (tmp_path / component.path / component.marker).write_text("x", encoding="utf-8")
    assert component.check(tmp_path)


def test_component_without_marker_checks_existence(tmp_path):
    from risarms_host.layout import Component

    bare = Component("docs", "RISARMS-DOCS")
    (tmp_path / "RISARMS-DOCS").mkdir()
    assert bare.check(tmp_path)
    assert not (tmp_path / "missing").exists()


def test_bundle_requirements_cover_install_contract(tmp_path):
    paths = {component.path for component in BUNDLE_REQUIREMENTS}
    assert paths == {
        "CORE-HOST",
        "CORE-CLIENT",
        "services",
        "deployment",
        "compatibility.json",
    }
    portal = next(c for c in BUNDLE_REQUIREMENTS if c.path == "CORE-HOST")
    assert portal.marker == "core/web/portal.html"
    assert not portal.check(tmp_path)
