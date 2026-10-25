# Installation

## Requirements
- Python 3.14+
- MacOS (primarily; Linux might work but I've never tested it)
- Docker (or [OrbStack](https://orbstack.dev/))

## Install Dependencies

```bash

export HYPERGOLIC_API_KEY="your-api-key"
export HYPERGOLIC_BASE_URL="https://api.anthropic.com"

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
## Install Hypergolic

uv tool install hypergolic
```

## Set Environment Variables

Hypergolic needs an API key and base URL. Add these to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) so they persist across sessions:

```bash
```

You can get an API key at [console.anthropic.com](https://console.anthropic.com/).

### Models (per tier)

Each model tier maps to a model ID. Defaults are the standard Anthropic IDs,
served by the `anthropic` provider (the direct API, or a proxy such as
LiteLLM at `HYPERGOLIC_BASE_URL`). Set your own IDs, and route a
tier to a different backend, with `App(models=...)` in `~/.hypergolic/main.py`:

```python
from hypergolic import App, ModelTier, TierModel

app = App(
    models={
        ModelTier.HIGH: TierModel(id="claude-opus-4-8"),
        ModelTier.EXTRA_HIGH: TierModel(
            id="us.anthropic.claude-fable-5",
            provider="bedrock",
            aws_profile="your-sso-profile",
            aws_region="us-east-1",
        ),
    },
)
```

Tiers you leave out keep their defaults. `provider` is `anthropic`, `bedrock`
(native AWS Bedrock), or `mantle` (Anthropic's managed AWS gateway); the
default is `anthropic`. Unset `aws_profile` / `aws_region` use the default AWS
credential chain. `max_tokens` (default 64000) caps output per request, and
`headers` adds HTTP headers to that tier's requests. With AWS SSO, run `aws sso login --profile <name>`
first. Changes apply after `restart`.

### Database

Hypergolic runs on PostgreSQL. By default it manages its own: at launch it
starts a pinned `postgres` container on the Docker runtime that sessions
already require (data persists on the `hypergolic-pgdata` volume, bound to
`127.0.0.1:54320`). If Docker isn't running, the launcher offers to start it.
No configuration is required.

To use your own Postgres instead, set `HYPERGOLIC_DATABASE_URL`:

```bash
export HYPERGOLIC_DATABASE_URL="postgresql://user:password@host:5432/hypergolic"
```

The runtime routes ORM work over `asyncpg` for genuine non-blocking I/O
(concurrency is bounded by the connection pool rather than a thread pool),
while schema migrations run over the synchronous `psycopg` driver — both are
derived automatically from the same URL — writing the driver yourself
(`postgresql+asyncpg://...` or `postgresql+psycopg://...`) works too. Point the
URL at an existing, empty database; Hypergolic creates the schema on first
launch but not the database itself.

## Initialize Your Assistant

```bash
hypergolic init
```

This creates `~/.hypergolic/` with a `main.py` that loads Hypergolic's built-in defaults — built-in commands (git, review, land, history), prompts, skills, roles, and workflows — via `app.use_defaults()`. The defaults live in the installed `hypergolic` package and are loaded from there, so `main.py` stays small and you customize by overriding rather than copying. `init` also sets up a `uv` virtual environment and adds a shell alias so you can launch with `h`.

Restart your shell (or run the `source` command printed by init).

## Verify Installation

```bash
h
```

This launches the assistant, running database migrations, starting the local server, and opening the desktop window.

## Updating

```bash
uv tool install --upgrade hypergolic
hypergolic update
```

The first command updates the `hypergolic` package. The second re-pins your harness to the new version and re-syncs its environment. Because the built-in defaults ship with the package and are loaded via `app.use_defaults()`, improved tools and prompts arrive automatically with the upgrade — nothing is copied into `~/.hypergolic`, and your files are never touched.

## Development Installation

To work on Hypergolic itself:

```bash
git clone https://github.com/RobertTownley/hypergolic.git
cd hypergolic
uv sync
```

Run in dev mode (rebuilds UI from source on each launch):

```bash
HYPERGOLIC_DEV_MODE=true uv run hypergolic-dev
```
