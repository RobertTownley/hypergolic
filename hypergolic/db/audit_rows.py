from hypergolic.db.engine import get_db
from hypergolic.db.models import Base


def insert(row: Base) -> None:
    with get_db() as db:
        db.add(row)
