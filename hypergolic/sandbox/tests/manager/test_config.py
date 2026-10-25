import re

import pytest

from hypergolic.sandbox.manager.provisioning import _cleanup_resolved_config, _compose_project_name, _expose_targets, _find_default_service, _inject_dynamic_port_publishing, _label_value, _parse_config, _resolved_config_path
from hypergolic.sandbox.manager.types import SandboxError
from hypergolic.sandbox.manager.provisioning import _external_volume_names


@pytest.mark.parametrize("session_id, sandbox_id, expected", [
    ("abc123-def456", "my-tool", "hgmytoolabc123def456"),
    ("CXPP279VEF4K", "python_lab", "hgpythonlabcxpp279vef4k"),
    ("a" * 40, "tool", "hgtool" + "a" * 12),
    ("abc123", "python_lab_uv", "hgpythonlabuvabc123"),
])
def test_compose_project_name(session_id, sandbox_id, expected):
    name = _compose_project_name(session_id, sandbox_id)
    assert name == expected
    assert re.match(r"^[a-z0-9]+$", name)


def test_parse_config(tmp_path):
    with pytest.raises(SandboxError, match="Sandbox config not found"):
        _parse_config("/nonexistent/path.yaml")
    for body in ("key: value\n", ""):
        f = tmp_path / "bad.yaml"
        f.write_text(body)
        with pytest.raises(SandboxError, match="Invalid sandbox config"):
            _parse_config(str(f))
    f = tmp_path / "valid.yaml"
    f.write_text("services:\n  app:\n    image: ubuntu\n")
    assert "services" in _parse_config(str(f))


@pytest.mark.parametrize("app_labels, proxy_labels", [
    ({"hypergolic.default": "true"}, None),
    (["hypergolic.default=true"], None),
    (None, {"hypergolic.role": "proxy"}),
    (None, ["hypergolic.role=proxy"]),
])
def test_find_default_service_resolves_app(app_labels, proxy_labels):
    services = {}
    if proxy_labels is not None:
        services["proxy"] = {"image": "nginx", "labels": proxy_labels}
    services["app"] = {"image": "ubuntu"} | ({"labels": app_labels} if app_labels else {})
    services.setdefault("db", {"image": "postgres"})
    assert _find_default_service({"services": services}) == "app"


@pytest.mark.parametrize("services", [
    {},
    {"proxy1": {"image": "nginx", "labels": {"hypergolic.role": "proxy"}}},
])
def test_find_default_service_no_suitable_service(services):
    with pytest.raises(SandboxError, match="No suitable service"):
        _find_default_service({"services": services})


def test_expose_targets_and_publishing():
    config = {"services": {
        "api": {"labels": {"hypergolic.expose": "api=8000,metrics=9000"}},
        "db": {"labels": {"hypergolic.description": "db"}},
    }}
    targets = _expose_targets(config)
    assert targets == {"api": ("api", 8000), "metrics": ("api", 9000)}
    _inject_dynamic_port_publishing(config, targets)
    ports = config["services"]["api"]["ports"]
    assert "127.0.0.1::8000" in ports and "127.0.0.1::9000" in ports
    assert "ports" not in config["services"]["db"]
    assert _expose_targets({"services": {"a": {"labels": {}}}}) == {}


def test_label_value_handles_list_and_dict():
    assert _label_value({"k": "v"}, "k") == "v"
    assert _label_value(["k=v", "x=y"], "x") == "y"
    assert _label_value(["k=v"], "missing") is None


def test_external_volume_names():
    config = {"volumes": {
        "uv-cache": {"name": "hypergolic-shared-uv-cache", "external": True},
        "unnamed-ext": {"external": True},
        "scratch": {},
        "bare": None,
    }}
    assert _external_volume_names(config) == ["hypergolic-shared-uv-cache", "unnamed-ext"]
    assert _external_volume_names({}) == []


def test_resolved_config_paths(tmp_path):
    canonical = tmp_path / "acme.compose.yaml"
    canonical.write_text("services: {}")
    p1 = _resolved_config_path(str(canonical), "hgreadyabc")
    assert p1 == _resolved_config_path(str(canonical), "hgreadyabc")
    assert p1.parent == tmp_path  # sibling of canonical (relative mounts resolve)

    resolved = tmp_path / ".hg-resolved-hgreadyabc.compose.yaml"
    resolved.write_text("services: {}")
    _cleanup_resolved_config(str(canonical))
    _cleanup_resolved_config(str(resolved))
    assert canonical.exists() and not resolved.exists()
