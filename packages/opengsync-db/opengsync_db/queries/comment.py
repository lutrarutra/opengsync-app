import sqlalchemy as sa

from ..models import Comment, Experiment, SeqRequest, LabPrep, MediaFile, User


def create(
    text: str,
    author: User,
    file: MediaFile | None = None,
    seq_request: SeqRequest | None = None,
    experiment: Experiment | None = None,
    lab_prep: LabPrep | None = None,
) -> Comment:
    return Comment(
        text=text.strip()[:4096],
        author=author,
        file=file,
        experiment=experiment,
        seq_request=seq_request,
        lab_prep=lab_prep
    )


def select(
    id: int | None = None,
    author_id: int | None = None,
    file_id: int | None = None,
    seq_request_id: int | None = None,
    experiment_id: int | None = None,
    lab_prep_id: int | None = None,
    statement: sa.Select[tuple[Comment]] = sa.select(Comment),
) -> sa.Select[tuple[Comment]]:
    statement = statement.where(*where_clauses(
        id=id,
        author_id=author_id,
        file_id=file_id,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
    ))
    return statement


def where_clauses(
    id: int | None = None,
    author_id: int | None = None,
    file_id: int | None = None,
    seq_request_id: int | None = None,
    experiment_id: int | None = None,
    lab_prep_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering comments.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Comment.id == id)
    if author_id is not None:
        clauses.append(Comment.author_id == author_id)
    if file_id is not None:
        clauses.append(Comment.file_id == file_id)
    if seq_request_id is not None:
        clauses.append(Comment.seq_request_id == seq_request_id)
    if experiment_id is not None:
        clauses.append(Comment.experiment_id == experiment_id)
    if lab_prep_id is not None:
        clauses.append(Comment.lab_prep_id == lab_prep_id)

    return clauses