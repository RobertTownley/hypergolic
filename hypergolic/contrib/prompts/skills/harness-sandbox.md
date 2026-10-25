Configure a **project sandbox** — the containerized environment the agent runs every shell command in. Sandboxing is the safety boundary: a destructive command is contained to a disposable environment, not the host.

## The model
The definitive signatures are in `/hypergolic/sandbox/model.py` (`ProjectSandbox`, `Container`, `Image`, `Port`, `Healthcheck`, `Volume`, `Network`, `Egress`, `HostMount`) — read it before authoring. Author the sandbox in the user's `main.py` and attach with `project.configure_sandbox(sandbox)`; it compiles to a generated Compose file (never hand-edit) and validates on construction, surfaced by `validate_harness`.

## Semantics to internalize
- **Three states**: no `configure_sandbox` call → built-in Ubuntu dev container with `Egress.DenyAll()`; `configure_sandbox(sandbox)` → used exactly as written; `configure_sandbox(None)` → no `cmd` tool at all (non-coding projects)
- **Egress is always default-deny** unless the project grants it: `DenyAll()` / `Allow([hosts])` (domain-level, via proxy) / `AllowAll()`. Containers always reach each other by service name regardless
- **No default container**: with multiple containers, `cmd` requires a `container` argument
- **Built-in mounts in every container**: session workspace rw `/app` (one shared tree; gitdir in a session volume at `/var/git`), per-session harness clone rw `/harness`, cross-session `/shared` rw, command interface ro `/tools`, Hypergolic source ro `/hypergolic`, host repos ro `/host-repos`. Other host dirs need `HostMount` (read-only by default; opt into writes explicitly)
- **`command_timeout`** overrides the 120s `cmd` default; raise it when slow pre-commit hooks make agents background commits
- **Resource limits**: `cpus=` / `mem_limit=` per container; unset = whole host. `nproc` ignores the CPU quota, so read `HG_CPUS` for worker counts. Idle JVMs are the usual memory cost: pair `mem_limit` with `-Xmx`
- **Dynamic ports**: `expose=[Port(...)]` allocates a free host port per session, surfaced in session context. Never hardcode a host port

## Advising the user
- **No external Dockerfiles**: `Container.image` is a registry ref (pull-only for `skip_workspace_mount` infra; workspace containers build FROM it) or `Image(steps=[...])` of verbatim instructions; a project reusing a Dockerfile reads its body into `steps`
- Dev images should carry the tooling agents need (git/node/etc); only uv/git/jq/ast-grep/`edit` (hypergolic/sandbox/edit.py) are injected at compile
- Point out hot reloading: the /app mount makes edits live if the dev server watches it
- Builds need egress: package registries must be in `Egress.Allow` or installs hang
- Build caching: prefer prebuilt image + /app bind mount; dependency installs before `COPY .`; BuildKit cache mounts for uv/pip/npm and apt indexes; lift toolchains from official images (`COPY --from=node:...`) rather than adding third-party apt repos
