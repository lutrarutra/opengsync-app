from fastapi import APIRouter, Depends, Query

from opengsync_db import SyncSession, queries as Q, categories as C, models

from ...core import dependencies, responses, query_options
from ... import forms
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Variant

router = APIRouter(prefix="/sequencers", tags=["sequencers"])


SQ = models.Sequencer


class SequencerTable(Table):
    key = "seqr"
    model = models.Sequencer
    noun = "sequencers"
    columns = [
        Col("id", "ID", sort=True, search=Exact(SQ.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(SQ.name, compact=True), hideable=False, size=5),
        Col("model", "Model", sort=True, filter=Enum(C.SequencerModel), size=3),
    ]
    variants = {
        "default": Variant(["id", "name", "model"], "components/tables/rows/sequencer.html", dom_id="sequencer-table"),
    }


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_sequencer_table(
    state: TableState = Depends(SequencerTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = SequencerTable(state, route="render_sequencer_table", user=current_user)
    return table.render(session, Q.sequencer.select())


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
    elif word:
        stmt = Q.sequencer.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Sequencer.name.asc())

    return query_options.search_response(session, stmt, page=page, option=query_options.sequencer_option)

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