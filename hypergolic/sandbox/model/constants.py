from __future__ import annotations

#: The project sandbox is registered under this tool id, which keys its
#: DBSandbox row — every caller that looks a sandbox up by session must agree.
SANDBOX_TOOL_ID = "cmd"

#: Every sandbox container carries ``hypergolic.session=<id>``, interpolated
#: from the per-session ``up`` env, so one key-only ``docker ps`` filter finds
#: all harness containers and names their session.
SESSION_ENV = "HYPERGOLIC_SESSION_ID"
SESSION_LABEL = "hypergolic.session"

WORKSPACE_MOUNT = "/app"
WORKSPACE_ENV = "HYPERGOLIC_WORKSPACE"

HARNESS_MOUNT = "/harness"
HARNESS_ENV = "HYPERGOLIC_HARNESS"

SHARED_MOUNT = "/shared"
SHARED_ENV = "HYPERGOLIC_SHARED"

# Read-only mounts of host repo gitdirs: the clone/fetch sources for the
# session's sandbox-owned repos (see docs/sandbox-lifecycle.md). Each is
# mounted at its host-true path so the single alternates line in clones and
# quarantines resolves identically in the container and on the host. The
# session gitdirs themselves live in a per-session compose volume mounted
# at GITDIR_MOUNT_ROOT -- container-only by design.
HOST_REPO_APP_ENV = "HYPERGOLIC_HOST_REPO_APP"
HOST_REPO_HARNESS_ENV = "HYPERGOLIC_HOST_REPO_HARNESS"
HOST_REPO_SHARED_ENV = "HYPERGOLIC_HOST_REPO_SHARED"
HOST_OBJECTS_APP_ENV = "HYPERGOLIC_HOST_OBJECTS_APP"

# Per-session bare quarantine repos (rw): the push transport out of the
# sandbox (see hypergolic.git.quarantine).
QUARANTINE_APP_ENV = "HYPERGOLIC_QUARANTINE_APP"
QUARANTINE_HARNESS_ENV = "HYPERGOLIC_QUARANTINE_HARNESS"
QUARANTINE_SHARED_ENV = "HYPERGOLIC_QUARANTINE_SHARED"

# The generated command interface: a flat bin/ of shims plus per-command docs.
# Read-only for provenance, not privilege -- the broker resolves against its own
# registry, so a shim the agent forges anywhere confers nothing.
TOOLS_MOUNT = "/tools"
TOOLS_ENV = "HYPERGOLIC_TOOLS"

# Hypergolic's own package source, so /tools/<name>/source resolves for built-in
# commands the way it does for harness-authored ones via /harness. Reading the
# code that will run host-side is the property that makes a command's approval
# posture predictable rather than something to discover by tripping it.
PACKAGE_MOUNT = "/hypergolic"
PACKAGE_ENV = "HYPERGOLIC_PACKAGE"

EGRESS_PROXY_SERVICE = "hypergolic-egress"
EGRESS_INTERNAL_NETWORK = "hypergolic_internal"
EGRESS_EXTERNAL_NETWORK = "hypergolic_egress"
EGRESS_PROXY_PORT = 3128
SQUID_IMAGE = "ubuntu/squid:6.6-24.04_edge"
