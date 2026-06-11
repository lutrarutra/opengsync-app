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
    statement = statement.where(*where_clauses(id=id))
    return statement


def where_clauses(
    id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering plates.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Plate.id == id)

    return clauses