from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

PROMPTS_DIR = Path(__file__).parent.parent / "contrib" / "prompts"

# The managed Postgres container's URL (see hypergolic.db.container, which
# derives its docker run arguments from this).
DEFAULT_DATABASE_URL = "postgresql://hypergolic:hypergolic@127.0.0.1:54320/hypergolic"
DEFAULT_OTEL_ENDPOINT = "http://127.0.0.1:54318"
DEFAULT_GRAFANA_URL = "http://127.0.0.1:54330"
DEFAULT_TRUNCATE_TOKEN_THRESHOLD = 50_000
DEFAULT_STRIP_HISTORY_THINKING = True
DEFAULT_TURN_COMPACTION_FLOOR_TOKENS = 5_000

# Hypergolic's own runtime state that should NOT be exposed to project
# sandboxes (which bind-mount ~/.hypergolic read-only at /harness). Lives in
# a sibling directory so the harness mount carries only configuration, never
# credentials or worktree contents.
HARNESS_DIR = Path.home() / ".hypergolic"
INTERNALS_DIR = Path.home() / ".hypergolic_internals"


def sessions_internals_root() -> Path:
    return INTERNALS_DIR / "sessions"


def session_internals_dir(session_id: str) -> Path:
    return sessions_internals_root() / session_id


# "bedrock"  -> native AWS Bedrock InvokeModel (bedrock-runtime.*.amazonaws.com)
# "mantle"   -> Anthropic's managed AWS gateway (bedrock-mantle.*.api.aws).
#              Uses the same AWS credentials and per-tier AWS settings as
#              "bedrock", but routes through Mantle, which some models (e.g.
#              claude-fable-5) require because native Bedrock's 'default' data
#              retention mode is unavailable for them.
Provider = Literal["anthropic", "bedrock", "mantle"]


class Settings(BaseSettings):
    HYPERGOLIC_API_KEY: str = ""
    # Loopback port uvicorn binds. Also the broker address sandbox shims dial
    # (host.docker.internal:HYPERGOLIC_PORT), so it must have exactly one
    # source of truth: an override that only the launcher saw would desync
    # every shim from the server it is supposed to reach.
    HYPERGOLIC_PORT: int = 54322
    HYPERGOLIC_BASE_URL: str = "https://api.anthropic.com"
    # Defaults to the managed Postgres container (hypergolic.db.container);
    # set explicitly to run against any other Postgres. The async runtime
    # uses asyncpg while migrations use psycopg, both derived from this URL.
    HYPERGOLIC_DATABASE_URL: str = DEFAULT_DATABASE_URL
    HYPERGOLIC_OTEL_ENDPOINT: str = DEFAULT_OTEL_ENDPOINT
    HYPERGOLIC_GRAFANA_URL: str = DEFAULT_GRAFANA_URL
    # Reaping tears down containers the DB says are orphaned; a process
    # whose DB is a throwaway (the test suite) must never do that.
    HYPERGOLIC_SANDBOX_REAP: bool = True
    HYPERGOLIC_WORKTREES_ROOT: str = str(INTERNALS_DIR / "worktrees")

    # Trusted-host autonomy mode. When true:
    #   - every REQUIRE_APPROVAL decision (harness tools, MCP tools, workflow
    #     transition gates) is auto-approved — nothing pauses for a human
    #   - project sandboxes are never created (worktrees still are); the
    #     sandbox `cmd` tool is removed and start_sandbox refuses to run
    #   - the structured `git` tool is removed (shell git works fine outside
    #     the sandbox) and every session — including children — gets the
    #     host shell, published as `cmd`
    # Only set this on machines where the execution environment is fully
    # trusted: the agent runs arbitrary shell commands on the host, with the
    # server's credentials and network access, unattended.
    HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE: bool = False

    # Static AWS credentials for tiers on "bedrock" / "mantle". If left
    # empty, the SDK uses the default AWS credential chain (env vars,
    # ~/.aws/credentials, SSO cache, instance profile, etc.).
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SESSION_TOKEN: str = ""


settings = Settings()
