"""Status tab of requests, projects, lab preps and experiments (staff only).

Where the record is on its route, which ways lead to the next status and what blocks them, the
statuses of its children, and its status history. Data comes from opengsync_db.transitions.
"""
from typing import Any

from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession, queries as Q
from opengsync_db.transitions import run_operation, entities, kanban, statechart, routes as transition_routes, status as transition_status, manual as manual_ops

from ...core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/status", tags=["status"])

_QUERIES = {
    "seq_request": Q.seq_request,
    "project": Q.project,
    "lab_prep": Q.lab_prep,
    "experiment": Q.experiment,
}

PAGE_TABS = {
    "seq_request": ("seq_request_page", "seq_request_id", "request-status-tab"),
    "project": ("project_page", "project_id", "project-status-tab"),
    "lab_prep": ("lab_prep_page", "lab_prep_id", "lab_prep-status-tab"),
    "experiment": ("experiment_page", "experiment_id", "experiment-status-tab"),
}


def _load(session: SyncSession, entity: str, obj_id: int) -> Any:
    if (query := _QUERIES.get(entity)) is None:
        raise exc.NotFoundException(f"No status tab for '{entity}'.")
    if (obj := session.first(query.select(id=obj_id))) is None:
        raise exc.NotFoundException()
    return obj


@router.get("/{entity}/{obj_id}")
def render_status(
    entity: str,
    obj_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    obj = _load(session, entity, obj_id)
    report = transition_status.build(session, obj)
    return responses.htmx_response(
        template="components/status/tab.html",
        report=report, obj=obj, entity_name=entity, routes=transition_routes.ROUTES,
        board=kanban.build(session, obj, report.entity),
    )


@router.get("/{entity}/{obj_id}/history")
def render_history(
    entity: str,
    obj_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    obj = _load(session, entity, obj_id)
    entries = transition_status.history(session, obj)
    actor_ids = {e.actor_id for e in entries if e.actor_id is not None}
    actors = {user.id: user for user in session.get_all(Q.user.select().where(models.User.id.in_(actor_ids)), limit=None)} if actor_ids else {}
    return responses.htmx_response(
        template="components/status/timeline.html",
        entries=entries, actors=actors, report_entity=transition_status.entity_of(obj), ENTITY_BY_NAME=entities.BY_NAME,
    )


@router.get("/{entity}/{obj_id}/statechart")
def render_statechart(
    entity: str,
    obj_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    """The entity's statuses (cards) and actions (edges), with this record's position on top (React Flow)."""
    obj = _load(session, entity, obj_id)
    chart = statechart.build(transition_status.build(session, obj), transition_status.history(session, obj, limit=500))
    return {
        "entity": chart.entity.label,
        "cards": [
            {
                "id": card.status.name,
                "label": card.status.display_name,
                "description": getattr(card.status, "description", ""),
                "rank": card.status.id,
                "side": card.side,
                "current": card.current,
                "visited": card.visited,
                "since": card.since.strftime("%Y-%m-%d") if card.since else None,
            }
            for card in chart.cards
        ],
        "transitions": [
            {
                "id": f"{t.source.name}->{t.target.name}",
                "source": t.source.name,
                "target": t.target.name,
                "state": t.state,
                "taken": t.taken,
                "fromCurrent": t.from_current,
                "actions": [
                    {
                        "id": a.operation.id,
                        "label": a.operation.label,
                        "kind": a.operation.kind.label,
                        "state": a.state,
                        "blockers": list(a.blockers),
                        "effects": list(a.other_effects),
                    }
                    for a in t.actions
                ],
            }
            for t in chart.transitions
        ],
    }


@router.post("/seq_request/{obj_id}/route")
def set_route(
    obj_id: int,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
):
    """Pin the route of a request, or clear the pin (empty value) to infer it again."""
    # the form body is parsed by the parse_form_data middleware
    route = str(getattr(request.state, "form_data", {}).get("route", "")).strip()
    seq_request = _load(session, "seq_request", obj_id)
    if route and route not in transition_routes.BY_ID:
        raise exc.BadRequestException(f"Unknown route '{route}'.")
    with run_operation(session, manual_ops.SET_ROUTE, subject=seq_request):
        seq_request.route_override = route or None
        session.save(seq_request)

    page, param, tab = PAGE_TABS["seq_request"]
    return responses.htmx_response(
        redirect=request.url_for(page, **{param: obj_id}).include_query_params(tab=tab),
        flash=responses.flash("Route pinned." if route else "Route is inferred again.", "success"),
    )
