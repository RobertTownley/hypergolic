from unittest.mock import AsyncMock, patch

from hypergolic.sandbox.manager.reap_networks import reap_orphaned_networks
from hypergolic.sandbox.manager.types import ExecResult


def _ok(stdout: str = "") -> ExecResult:
    return ExecResult(stdout=stdout, stderr="", returncode=0)


def _docker(networks: dict[str, str], occupied: list[str]) -> AsyncMock:
    listing = "".join(f"{n}\t{p}\n" for n, p in networks.items())

    async def _run(*args, **kwargs):
        if args[0] == "ps":
            return _ok("\n".join(occupied))
        if args[:2] == ("network", "ls"):
            return _ok(listing)
        return _ok()

    return AsyncMock(side_effect=_run)


def _removed(mock: AsyncMock) -> list[str]:
    return [c.args[2] for c in mock.await_args_list if c.args[:2] == ("network", "rm")]


async def test_removes_only_empty_unprotected_hypergolic_networks():
    docker = _docker(
        {
            "hgcmdgone_internal": "hgcmdgone",
            "hgcmdgone_egress": "hgcmdgone",
            "hgcmdlive_internal": "hgcmdlive",
            "hgcmdstarting_internal": "hgcmdstarting",
            "acme-pilot_default": "acme-pilot",
        },
        occupied=["hgcmdlive"],
    )
    with patch("hypergolic.sandbox.manager.docker._run_docker", docker):
        assert await reap_orphaned_networks({"hgcmdstarting"}) == 2

    assert _removed(docker) == ["hgcmdgone_egress", "hgcmdgone_internal"]


async def test_skips_when_container_listing_fails():
    async def _run(*args, **kwargs):
        if args[0] == "ps":
            return ExecResult(stdout="", stderr="boom", returncode=1)
        return _ok("hgcmdgone_internal\thgcmdgone\n")

    docker = AsyncMock(side_effect=_run)
    with patch("hypergolic.sandbox.manager.docker._run_docker", docker):
        assert await reap_orphaned_networks(set()) == 0
    assert _removed(docker) == []
