from unittest.mock import patch

import pytest
import sqlalchemy as sa

from hypergolic.config.settings import settings
from hypergolic.cli.setup import _package_root
from hypergolic.db.engine import sync_url
from hypergolic.db.models import Base
from tests.helpers.pg import scratch_database

pytestmark = pytest.mark.db


def _migrated_engine(url: str):
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_package_root() / "alembic"))
    with patch.object(settings, "HYPERGOLIC_DATABASE_URL", url):
        command.upgrade(cfg, "head")
    return sa.create_engine(sync_url(url))


@pytest.mark.timeout(30)
def test_upgrade_head_matches_models():
    with scratch_database("migrations") as url:
        inspector = sa.inspect(_migrated_engine(url))
        for table in Base.metadata.sorted_tables:
            migrated = {c["name"] for c in inspector.get_columns(table.name)}
            declared = {c.name for c in table.columns}
            assert migrated == declared, f"{table.name}: alembic vs models drift"
