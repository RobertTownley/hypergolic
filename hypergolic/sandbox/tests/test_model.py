"""Tests for hypergolic.sandbox.model and compose compilation."""

import pytest

from hypergolic.sandbox.exec_env import server_port
from hypergolic.sandbox.compose import compile_compose, render_squid_conf
from hypergolic.sandbox.model.containers import (
    Container,
    Healthcheck,
    HostMount,
    Image,
    Network,
    Port,
    Volume,
)
from hypergolic.sandbox.model.egress import Egress, EgressMode
from hypergolic.sandbox.model.sandbox import (
    DEFAULT_SANDBOX_ID,
    ProjectSandbox,
    REQUIRED_BUILD_STEPS,
    default_sandbox,
)


def test_to_compose_mounts_app_and_default_label():
    sb = ProjectSandbox(
        id="s",
        containers=[
            Container(id="api", image=Image(base="x"),
                      expose=[Port(container=8000, name="api")],
                      healthcheck=Healthcheck(test="curl -f http://localhost:8000")),
            Container(id="db", image="postgres:16"),
        ],
        volumes=[Volume(id="pgdata", mounts={"db": "/var/lib/postgresql/data"})],
    )
    compose = compile_compose(sb)
    api = compose["services"]["api"]
    # Mount is present; working_dir is set per-exec, not on the service.
    assert "working_dir" not in api
    assert "${HYPERGOLIC_WORKSPACE:-.}:/app:rw" in api["volumes"]
    # The harness (~/.hypergolic) is mounted read-only at /harness everywhere.
    assert "${HYPERGOLIC_HARNESS:-/dev/null}:/harness:rw" in api["volumes"]
    assert "${HYPERGOLIC_HARNESS:-/dev/null}:/harness:rw" in compose["services"]["db"]["volumes"]
    # The persistent per-project shared dir is mounted RW at /shared everywhere
    # the workspace is mounted.
    assert "${HYPERGOLIC_SHARED:-/dev/null}:/shared:rw" in api["volumes"]
    assert "${HYPERGOLIC_SHARED:-/dev/null}:/shared:rw" in compose["services"]["db"]["volumes"]
    assert api["labels"]["hypergolic.default"] == "true"
    assert "hypergolic.default" not in compose["services"]["db"]["labels"]
    assert "pgdata:/var/lib/postgresql/data" in compose["services"]["db"]["volumes"]
    assert api["healthcheck"]["test"] == ["CMD-SHELL", "curl -f http://localhost:8000"]
    assert compose["volumes"] == {"hg-gitdir": {}, "pgdata": {}}


def test_built_services_get_a_tag_keyed_on_the_sandbox_not_the_session():
    """Compose would otherwise derive the tag from the per-session project name,
    rebuilding and storing one image per session."""
    sb = ProjectSandbox(
        id="acme-sandbox",
        containers=[
            Container(id="dev", image=Image(base="x")),
            Container(id="db", image="postgres:17", skip_workspace_mount=True),
        ],
    )
    services = compile_compose(sb)["services"]
    assert services["dev"]["image"] == "hg-acme-sandbox-dev:latest"
    assert services["db"]["image"] == "postgres:17"


def test_workspace_registry_ref_gains_required_build_steps():
    """A plain registry ref on a workspace container still gets the uv
    contract: compiled to a build whose dockerfile is FROM <ref> + required."""
    sb = ProjectSandbox(id="s", containers=[Container(id="dev", image="node:24")])
    svc = compile_compose(sb)["services"]["dev"]
    assert svc["image"] == "hg-s-dev:latest"
    assert svc["build"]["dockerfile_inline"] == f"FROM node:24\n{REQUIRED_BUILD_STEPS}"
    assert svc["build"]["context"] == "hg-empty-context"


def test_image_renders_steps_then_required_steps_then_user():
    """The structural guarantee: required steps run after authored steps but
    before the final USER, so a non-root user can't break the toolchain."""
    img = Image(base="x", steps=["RUN a", "RUN b"], user="dev", context="/ctx",
                args={"K": "v"})
    sb = ProjectSandbox(id="s", containers=[Container(id="dev", image=img)])
    build = compile_compose(sb)["services"]["dev"]["build"]
    assert build["context"] == "/ctx"
    assert build["args"] == {"K": "v"}
    assert build["dockerfile_inline"] == (
        f"FROM x\nRUN a\nRUN b\n{REQUIRED_BUILD_STEPS}USER dev\n"
    )


def test_image_additional_contexts_reach_the_build_section():
    img = Image(base="x", additional_contexts={"app": "/home/u/proj"})
    sb = ProjectSandbox(id="s", containers=[Container(id="dev", image=img)])
    build = compile_compose(sb)["services"]["dev"]["build"]
    assert build["additional_contexts"] == {"app": "/home/u/proj"}
    assert "additional_contexts" not in compile_compose(
        ProjectSandbox(id="s2", containers=[Container(id="dev", image=Image(base="x"))])
    )["services"]["dev"]["build"]


def test_skip_workspace_mount_registry_ref_is_pull_only():
    """Stock infra images (postgres etc.) are pulled verbatim, never built."""
    sb = ProjectSandbox(
        id="s",
        containers=[
            Container(id="dev", image="node:24"),
            Container(id="db", image="postgres:17", skip_workspace_mount=True),
        ],
    )
    db = compile_compose(sb)["services"]["db"]
    assert db["image"] == "postgres:17"
    assert "build" not in db


def test_skip_workspace_mount_authored_image_builds_without_required_steps():
    """Infra containers can author an Image; they build but carry no agent
    toolchain contract."""
    img = Image(base="postgres:17", steps=["RUN echo tuning"], user="postgres")
    sb = ProjectSandbox(
        id="s", containers=[Container(id="db", image=img, skip_workspace_mount=True)]
    )
    svc = compile_compose(sb)["services"]["db"]
    assert svc["image"] == "hg-s-db:latest"
    assert svc["build"]["dockerfile_inline"] == (
        "FROM postgres:17\nRUN echo tuning\nUSER postgres\n"
    )


def test_default_sandbox_compiles_with_required_build_steps():
    inline = compile_compose(default_sandbox())["services"]["dev"]["build"]["dockerfile_inline"]
    assert inline.endswith(REQUIRED_BUILD_STEPS)
    assert "command -v uv" in inline
    assert 'ln -sf "$(uv python find --managed-python' in inline
    assert "/usr/local/bin/hg-python" in inline
    assert "/hypergolic/sandbox/edit.py" in inline and "/usr/local/bin/edit" in inline


def test_internal_network_compiles():
    sb = ProjectSandbox(
        id="s",
        containers=[Container(id="a", image="x", networks=["backend"])],
        networks=[Network(id="backend", internal=True)],
    )
    assert compile_compose(sb)["networks"]["backend"] == {"internal": True}


def test_container_ids_order_preserved():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="z", image="x"), Container(id="a", image="y")])
    assert sb.container_ids == ["z", "a"]


@pytest.mark.parametrize("kwargs, frag", [
    (dict(id="s", containers=[]), "at least one container"),
    (dict(id="s", containers=[Container(id="a", image="x"), Container(id="a", image="y")]),
     "duplicate container ids"),
    (dict(id="s", containers=[Container(id="a", image="x", depends_on=["z"])]),
     "unknown container 'z'"),
    (dict(id="s", containers=[Container(id="a", image="x", networks=["n"])]),
     "unknown network 'n'"),
])
def test_sandbox_validation_errors(kwargs, frag):
    with pytest.raises(ValueError, match=frag):
        ProjectSandbox(**kwargs)


def test_duplicate_port_names_rejected():
    with pytest.raises(ValueError, match="duplicate exposed port names"):
        ProjectSandbox(id="s", containers=[
            Container(id="a", image="x", expose=[Port(container=1, name="p")]),
            Container(id="b", image="y", expose=[Port(container=2, name="p")]),
        ])


def test_image_steps_cannot_declare_build_stages():
    with pytest.raises(ValueError, match="cannot declare build stages"):
        Image(base="x", steps=["FROM node:22 AS node"])


def test_container_requires_an_image():
    with pytest.raises(ValueError, match="image"):
        Container.model_validate({"id": "a"})


def test_egress_factories():
    assert Egress.DenyAll().mode is EgressMode.DENY_ALL
    assert Egress.AllowAll().mode is EgressMode.ALLOW_ALL
    a = Egress.Allow(["https://pypi.org"])
    assert a.mode is EgressMode.ALLOW and a.hosts == ["https://pypi.org"]


@pytest.mark.parametrize("factory, frag", [
    (lambda: Egress.Allow([]), "at least one host"),
    (lambda: Egress(mode=EgressMode.DENY_ALL, hosts=["x"]), "only meaningful"),
])
def test_egress_validation(factory, frag):
    with pytest.raises(ValueError, match=frag):
        factory()


def test_expose_emits_label():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="api", image="x",
                  expose=[Port(container=8000, name="api"), Port(container=9000, name="metrics")])])
    label = compile_compose(sb)["services"]["api"]["labels"]["hypergolic.expose"]
    assert label == "api=8000,metrics=9000"


def test_allow_all_egress_no_proxy():
    sb = ProjectSandbox(id="s", containers=[Container(id="a", image="x")],
                        egress=Egress.AllowAll())
    compose = compile_compose(sb)
    assert "hypergolic-egress" not in compose["services"]
    assert render_squid_conf(sb.egress) is None
    assert "HTTP_PROXY" not in compose["services"]["a"].get("environment", {})


def test_restricted_egress_compiles_proxy_and_env():
    sb = ProjectSandbox(id="s",
        containers=[Container(id="a", image="x"), Container(id="b", image="y")],
        egress=Egress.Allow(["https://pypi.org", "https://registry.npmjs.org"]))
    compose = compile_compose(sb)
    assert "hypergolic-egress" in compose["services"]
    proxy = compose["services"]["hypergolic-egress"]
    assert proxy["labels"]["hypergolic.role"] == "proxy"
    assert "hypergolic_internal" in proxy["networks"] and "hypergolic_egress" in proxy["networks"]
    a = compose["services"]["a"]
    assert a["environment"]["HTTPS_PROXY"] == "http://hypergolic-egress:3128"
    no_proxy = a["environment"]["NO_PROXY"].split(",")
    assert "hypergolic-egress" in no_proxy  # proxy reaches itself directly
    assert {"a", "b", "localhost", "127.0.0.1"} <= set(no_proxy)
    assert "host.docker.internal" not in no_proxy  # broker traffic goes through squid
    assert proxy["extra_hosts"] == ["host.docker.internal:host-gateway"]
    assert "hypergolic_internal" in a["networks"]
    assert "hypergolic-egress" in a["depends_on"]
    assert compose["networks"]["hypergolic_internal"] == {"internal": True}
    assert compose["networks"]["hypergolic_egress"] == {}


def test_squid_conf_allowlist():
    conf = render_squid_conf(Egress.Allow(["https://pypi.org", "https://files.pythonhosted.org:443"]))
    assert conf is not None
    # A leading-dot dstdomain matches the apex and all subdomains. The bare
    # apex must NOT also be listed: Squid 6 fatally rejects it as redundant.
    assert "acl allowed_domains dstdomain .pypi.org" in conf
    assert "acl allowed_domains dstdomain .files.pythonhosted.org" in conf
    assert "acl allowed_domains dstdomain pypi.org\n" not in conf
    assert "acl allowed_domains dstdomain files.pythonhosted.org\n" not in conf
    assert "http_access allow allowed_domains" in conf
    assert conf.strip().endswith("http_access deny all")
    # The ubuntu/squid image runs squid as the unprivileged "proxy" user, which
    # cannot open /dev/stdout; logging there aborts startup. Log to the file the
    # image entrypoint already tails to stdout instead.
    assert "/dev/stdout" not in conf
    assert "access_log daemon:/var/log/squid/access.log squid" in conf


def test_squid_conf_deny_all_has_no_allow():
    conf = render_squid_conf(Egress.DenyAll())
    assert conf is not None
    assert "http_access allow allowed_domains" not in conf
    assert "http_access deny all" in conf


@pytest.mark.parametrize("egress", [Egress.DenyAll(), Egress.Allow(["https://pypi.org"])])
def test_squid_conf_always_reaches_the_broker(egress):
    """Host commands run over plain HTTP to a non-standard port, and squid
    rejects a port outside Safe_ports before any allow rule is consulted."""
    conf = render_squid_conf(egress)
    assert conf is not None
    port = server_port()
    assert f"acl Safe_ports port 80 443 {port}" in conf
    assert "acl broker dstdomain host.docker.internal" in conf
    assert f"acl broker_port port {port}" in conf
    # An approval can hold the stream idle for as long as the human takes.
    assert "read_timeout 1 day" in conf
    broker_allow = conf.index("http_access allow broker broker_port")
    assert broker_allow < conf.index("http_access deny all")


def test_restricted_egress_forces_user_networks_internal():
    sb = ProjectSandbox(id="s",
        containers=[Container(id="a", image="x", networks=["pub"])],
        networks=[Network(id="pub")],
        egress=Egress.Allow(["https://pypi.org"]))
    compose = compile_compose(sb)
    assert compose["networks"]["pub"] == {"internal": True}


@pytest.mark.parametrize("host, expected", [
    ("https://pypi.org", "pypi.org"),
    ("pypi.org", "pypi.org"),
    ("https://files.pythonhosted.org:443", "files.pythonhosted.org"),
    ("registry.npmjs.org:8080", "registry.npmjs.org"),
    ("https://example.com/path/here", "example.com"),
])
def test_egress_domain_extraction(host, expected):
    assert Egress.domain(host) == expected


def test_skip_workspace_mount_omits_app_mount():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="api", image="x"),
        Container(id="db", image="postgres:16", skip_workspace_mount=True,
                  ),
    ], volumes=[Volume(id="pgdata", mounts={"db": "/var/lib/postgresql/data"})])
    compose = compile_compose(sb)
    api = compose["services"]["api"]
    db = compose["services"]["db"]
    assert "working_dir" not in api
    assert any(":/app:rw" in v for v in api["volumes"])
    # db opts out of the /app mount but keeps its named volume
    assert "working_dir" not in db
    app_mounts = [v for v in db["volumes"] if v.endswith(":/app:rw")]
    assert app_mounts == []  # explicitly no /app mount
    # Opting out of the workspace mount also drops the /harness mount.
    assert [v for v in db["volumes"] if v.endswith(":/harness:rw")] == []
    # ...and the /shared mount.
    assert [v for v in db["volumes"] if v.endswith(":/shared:rw")] == []
    assert any(":/harness:rw" in v for v in api["volumes"])
    assert any(":/shared:rw" in v for v in api["volumes"])
    assert "pgdata:/var/lib/postgresql/data" in db["volumes"]


def test_default_sandbox_mounts_workspace_and_denies_egress():
    sb = default_sandbox()
    assert sb.id == DEFAULT_SANDBOX_ID
    assert sb.egress.mode is EgressMode.DENY_ALL
    compose = compile_compose(sb)
    dev = compose["services"]["dev"]
    # The agent's git dir must be mounted at /app, like every other sandbox.
    assert any(":/app:rw" in v for v in dev.get("volumes", []))


def test_default_sandbox_returns_fresh_instances():
    # No shared mutable singleton: each call is independent.
    assert default_sandbox() is not default_sandbox()


def test_host_mount_compiles_ro_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    sb = ProjectSandbox(
        id="s",
        containers=[
            Container(
                id="dev",
                image="ubuntu",
                host_mounts=[
                    HostMount(source="~/acme", target="/acme"),
                    HostMount(source="/opt/data", target="/data", read_only=False),
                ],
            )
        ],
    )
    vols = compile_compose(sb)["services"]["dev"]["volumes"]
    assert {
        "type": "bind",
        "source": f"{tmp_path}/acme",
        "target": "/acme",
        "read_only": True,
    } in vols
    assert {
        "type": "bind",
        "source": "/opt/data",
        "target": "/data",
        "read_only": False,
    } in vols


@pytest.mark.parametrize(
    "kwargs, frag",
    [
        ({"source": "", "target": "/x"}, "source must be an absolute"),
        ({"source": "data", "target": "/x"}, "source must be an absolute"),
        ({"source": "~/acme", "target": "acme"}, "target must be absolute"),
        ({"source": "~/acme", "target": "/app"}, "built-in mount"),
        ({"source": "~/acme", "target": "/shared/"}, "built-in mount"),
    ],
)
def test_host_mount_validation(kwargs, frag):
    with pytest.raises(ValueError, match=frag):
        HostMount(**kwargs)


def test_duplicate_host_mount_targets_rejected():
    with pytest.raises(ValueError, match="duplicate host mount targets"):
        Container(
            id="dev",
            image="ubuntu",
            host_mounts=[
                HostMount(source="/a", target="/x"),
                HostMount(source="/b", target="/x/"),
            ],
        )


def test_shared_volume_renders_external_with_stable_name():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="dev", image="ubuntu"),
    ], volumes=[
        Volume(id="uv-cache", shared=True, mounts={"dev": "/root/.cache/uv"}),
        Volume(id="scratch", mounts={"dev": "/scratch"}),
    ])
    compose = compile_compose(sb)
    assert compose["volumes"]["uv-cache"] == {
        "name": "hypergolic-shared-uv-cache", "external": True,
    }
    assert compose["volumes"]["scratch"] == {}
    dev = compose["services"]["dev"]
    assert "uv-cache:/root/.cache/uv" in dev["volumes"]
    assert "scratch:/scratch" in dev["volumes"]




def test_resource_limits_render_and_export_hg_cpus():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="dev", image="ubuntu", cpus=2.5, mem_limit="4g"),
        Container(id="db", image="postgres:17", skip_workspace_mount=True),
    ])
    services = compile_compose(sb)["services"]
    assert services["dev"]["cpus"] == 2.5
    assert services["dev"]["mem_limit"] == "4g"
    assert services["dev"]["environment"]["HG_CPUS"] == "3"
    assert not {"cpus", "mem_limit"} & services["db"].keys()


def test_authored_hg_cpus_wins():
    sb = ProjectSandbox(id="s", containers=[
        Container(id="dev", image="ubuntu", cpus=4, environment={"HG_CPUS": "2"}),
    ])
    assert compile_compose(sb)["services"]["dev"]["environment"]["HG_CPUS"] == "2"


@pytest.mark.parametrize("bad", [{"cpus": 0}, {"cpus": -1}, {"mem_limit": "4 GB"}, {"mem_limit": "0m"}])
def test_resource_limits_reject_bad_values(bad):
    with pytest.raises(ValueError):
        Container(id="dev", image="ubuntu", **bad)
