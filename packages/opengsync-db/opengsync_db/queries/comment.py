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
    author: User | None = None,
    file: MediaFile | None = None,
    seq_request: SeqRequest | None = None,
    experiment: Experiment | None = None,
    lab_prep: LabPrep | None = None,
    statement: sa.Select[tuple[Comment]] = sa.select(Comment),
) -> sa.Select[tuple[Comment]]:
    if id is not None:
        statement = statement.where(Comment.id == id)
    if author is not None:
        statement = statement.where(Comment.author_id == author.id)
    if file is not None:
        statement = statement.where(Comment.file_id == file.id)
    if seq_request is not None:
        statement = statement.where(Comment.seq_request_id == seq_request.id)
    if experiment is not None:
        statement = statement.where(Comment.experiment_id == experiment.id)
    if lab_prep is not None:
        statement = statement.where(Comment.lab_prep_id == lab_prep.id)
    return statement