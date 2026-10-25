Verify a project's harness actually works — and diagnose it when it doesn't. Docker runs on the host, not in containers: inspection goes through host-side tools.

## Probe ladder — escalate only as far as the question requires
1. **Static** (free): config on disk — git root, prompt paths, sandbox model, egress policy, mounts
2. **Smoke** (seconds, Docker, no LLM): `run_readiness_probes` execs real commands in the project sandbox — container reachability, /app rw, git, detected test runners installed, egress matching policy — and emits a scorecard with a concrete fix per failure
3. **Full simulation** (minutes, LLM dollars): conduct a simulated session in the project (`activate_skill evaluation`) to see how an agent *behaves* at a gap. Spawns real sessions — get user consent first

Structural config issues (duplicate ids, missing files, type errors) belong to `validate_harness`.

## Diagnosing a sandbox that hangs or misbehaves — stop at the first broken rung
A `ProjectSandbox` compiles to `~/.hypergolic_internals/sandboxes/<config-id>.compose.yaml`, with a per-session resolved copy (dynamic ports injected) beside it. Compose project name: `hg` + sandbox id + first 12 chars of session id, lowercased. Lifecycle is lazy: first exec runs `up -d`; a failed `up` auto-tears-down partial state. DB truth is the `sandboxes` table (`history`): `status`, `compose_project`, `config_path`, `port_map`.

1. **Daemon**: `docker info`
2. **Compose view**: `docker compose -p <proj> -f <resolved-config> ps -a`; exited → `docker logs <name>`; stuck `Created`/unhealthy → healthcheck or `depends_on` gate
3. **Config**: read the resolved compose file — wrong image, bad healthcheck, missing env show up before any container starts; cross-check the `ProjectSandbox`
4. **Image**: pull failures surface in `up` stderr; for slow builds, `docker buildx history ls` / `logs <id>` show per-step timings
5. **Exec basics**: `docker exec <name> sh -c 'true'`, then `ls /app` — empty /app means workspace env unset or wrong worktree path
6. **Egress**: squid answers 403 for non-allowlisted domains (policy, not breakage); allowlisted failures → `docker logs <proj>-hypergolic-egress-1`. Allowlisting is domain-level; only proxy-honoring clients work
7. **Ports**: dynamic per session — truth is `port_map` in the DB or `docker compose -p <proj> port <svc> <port>`

Name the root cause and its layer (daemon / compose config / ProjectSandbox / image / egress), fix it in the harness (`activate_skill harness-sandbox`), then re-run `run_readiness_probes`.
