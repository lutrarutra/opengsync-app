import sqlalchemy as sa

from ..models import Sequencer
from ..categories import SequencerModel


def create(
    name: str,
    model: SequencerModel,
    ip: str | None = None,
) -> Sequencer:
    return Sequencer(
        name=name.strip(),
        model_id=model.id,
        ip=ip.strip() if ip else None
    )


def select(
    id: int | None = None,
    model: SequencerModel | None = None,
    model_in: list[SequencerModel] | None = None,
    search_name: str | None = None,
    statement: sa.Select[tuple[Sequencer]] = sa.select(Sequencer),
) -> sa.Select[tuple[Sequencer]]:
    if id is not None:
        statement = statement.where(Sequencer.id == id)
    if model is not None:
        statement = statement.where(Sequencer.model_id == model.id)
    if model_in is not None:
        statement = statement.where(Sequencer.model_id.in_([m.id for m in model_in]))

    if search_name is not None:
        statement = statement.order_by(sa.nulls_last(sa.func.similarity(Sequencer.name, search_name).desc()))
    return statement