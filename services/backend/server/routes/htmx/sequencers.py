from fastapi import APIRouter, Depends, Query

from opengsync_db import SyncSession, queries as Q, categories as C, utils, models

from ...core import dependencies, responses
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/sequencers", tags=["sequencers"])


class SequencerTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Model", label="model", col_size=2, choices=C.SequencerModel.as_selectable(), sortable=True, sort_by="model_id"),
    ]


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_sequencer_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Sequencer, default=models.Sequencer.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = SequencerTable(route="render_sequencer_table", page=page, order_by=order_by)
    table.template = "components/tables/sequencer.html"
    stmt = Q.sequencer.select()
    sequencers = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(sequencers=sequencers)


@router.get("/search", dependencies=[Depends(dependencies.require_insider)])
def search_sequencers(
    word: str | None = Query(None, description="Search word for sequencer name"),
    selected_id: int | None = Query(None, description="Currently selected sequencer"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.sequencer.select()

    if selected_id is not None and not word:
        stmt = Q.sequencer.select(id=selected_id, statement=stmt)
    elif word is not None:
        stmt = Q.sequencer.search(name=word, statement=stmt)

    sequencers, _ = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/sequencer.html", sequencers=sequencers)

@router.delete("/{sequencer_id}/delete", dependencies=[Depends(dependencies.require_insider)])
def delete_sequencer(
    sequencer_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    sequencer = session.get_one(Q.sequencer.select(id=sequencer_id))
    session.delete(sequencer)
    return responses.htmx_response(
        redirect=responses.url_for("sequencers_page"),
        flash=responses.flash("Sequencer deleted.", "success")
    )

router.include_router(forms.models.SequencerForm.Router())