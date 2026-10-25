"""Validate that Alembic migrations form a single linear chain."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _alembic_config() -> Config:
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    config = Config(str(ini_path))
    return config


def test_only_single_head_revision_in_migrations():
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    # get_current_head() raises if there are multiple heads
    script.get_current_head()
