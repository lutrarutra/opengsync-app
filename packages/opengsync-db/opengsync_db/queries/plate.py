import sqlalchemy as sa

from ..models import Plate, User


def create(
    name: str,
    num_cols: int,
    num_rows: int,
    owner: User
) -> Plate:
    return Plate(name=name, num_cols=num_cols, num_rows=num_rows, owner=owner)


def select(
    id: int | None = None,
    statement: sa.Select[tuple[Plate]] = sa.select(Plate),
) -> sa.Select[tuple[Plate]]:
    if id is not None:
        statement = statement.where(Plate.id == id)
    return statement