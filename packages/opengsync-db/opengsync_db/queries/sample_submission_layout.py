import sqlalchemy as sa

from ..models import SampleSubmissionLayout


def select(
    seq_request_id: int | None = None,
    statement: sa.Select[SampleSubmissionLayout] = sa.select(SampleSubmissionLayout),
) -> sa.Select[SampleSubmissionLayout]:
    statement = statement.where(*where_clauses(seq_request_id=seq_request_id))
    return statement


def where_clauses(
    seq_request_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering submission layout entries.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if seq_request_id is not None:
        clauses.append(SampleSubmissionLayout.seq_request_id == seq_request_id)

    return clauses
