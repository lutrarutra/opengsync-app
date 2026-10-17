"""Kanban board of a record's contents: one column per status of its child records, one card per record.

A project's requests, an experiment's pools, a lab prep's libraries: their own statuses say little
(they are coarse or set by the status worker); where the work stands is in their contents. The
board is read-only and pure data for the Status tab. It costs a fixed number of queries (counts,
cards, last status changes, details), plus one status report per request on a project board.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa

from ..categories import ExtendedEnum, LibraryStatus, PoolStatus, SeqRequestStatus
from . import entities as E, relations as R
from .core import Entity
from .relations import Relation
from .status import NORMAL_STATUS_LIMIT

BOARDS: dict[str, Relation] = {
    E.PROJECT.name: R.PROJECT_REQUESTS,
    E.EXPERIMENT.name: R.EXPERIMENT_POOLS,
    E.LAB_PREP.name: R.PREP_LIBRARIES,
}

FIRST_COLUMN: dict[str, ExtendedEnum] = {
    # earlier statuses get a column only when a record is in one
    E.PROJECT.name: SeqRequestStatus.SUBMITTED,
    E.EXPERIMENT.name: PoolStatus.STORED,
    E.LAB_PREP.name: LibraryStatus.PREPARING,
}

BASELINE = "migration.baseline"
"""Its changes say what the status was at the migration, not when it was set: no age from them."""

CARD_LIMIT = 40
"""Cards shown per column; the rest are counted."""
NEXT_STEP_LIMIT = 25
"""Request cards get their next step only up to this many requests (one status report each)."""

_SEQUENCED = (LibraryStatus.SEQUENCED, LibraryStatus.SHARED, LibraryStatus.ARCHIVED)


@dataclass
class Card:
    id: int
    name: str
    status: ExtendedEnum
    since: datetime | None = None
    """When the record got its current status (from its status history)."""
    details: list[str] = field(default_factory=list)
    next_step: str | None = None
    group: str | None = None
    """Libraries: the request they belong to (cards are grouped by it)."""

    @property
    def days_in_status(self) -> int | None:
        return (datetime.now(timezone.utc) - self.since).days if self.since is not None else None


@dataclass
class Column:
    status: ExtendedEnum | None
    """None for the column of side states (failed, rejected, archived, …)."""
    cards: list[Card]
    total: int

    @property
    def hidden(self) -> int:
        return self.total - len(self.cards)


@dataclass
class Board:
    relation: Relation
    columns: list[Column]

    @property
    def child(self) -> Entity:
        return self.relation.child

    @property
    def total(self) -> int:
        return sum(c.total for c in self.columns)


def _since(session: Any, entity: Entity, cards: list[Card]) -> None:
    from .. import models
    SC, OR = models.StatusChange, models.OperationRun
    if not cards:
        return
    stmt = (
        sa.select(SC.entity_id, SC.to_status, sa.func.max(SC.timestamp_utc))
        .join(OR, OR.id == SC.run_id)
        .where(SC.entity_type == entity.name, SC.entity_id.in_([c.id for c in cards]), OR.operation != BASELINE)
        .group_by(SC.entity_id, SC.to_status)
    )
    latest = {(entity_id, to_status): ts for entity_id, to_status, ts in session.execute(stmt)}
    for card in cards:
        card.since = latest.get((card.id, card.status.id))


def _request_details(session: Any, cards: list[Card]) -> None:
    from .. import models
    from . import status as status_module
    L = models.Library
    ids = [c.id for c in cards]
    stmt = (
        sa.select(
            L.seq_request_id, sa.func.count(),
            sa.func.count().filter(L.status.in_(_SEQUENCED)),
            sa.func.count().filter(L.status == LibraryStatus.FAILED),
        )
        .where(L.seq_request_id.in_(ids)).group_by(L.seq_request_id)
    )
    progress = {rid: (total, done, failed) for rid, total, done, failed in session.execute(stmt)}
    for card in cards:
        total, done, failed = progress.get(card.id, (0, 0, 0))
        if total:
            card.details.append(f"{done}/{total} libraries sequenced")
        if failed:
            card.details.append(f"{failed} failed")
    if len(cards) <= NEXT_STEP_LIMIT:
        requests = {r.id: r for r in session.scalars(sa.select(models.SeqRequest).where(models.SeqRequest.id.in_(ids)))}
        for card in cards:
            if card.status.id < NORMAL_STATUS_LIMIT and (request := requests.get(card.id)) is not None:
                card.next_step = status_module.build(session, request).next_title


def _pool_details(session: Any, obj: Any, cards: list[Card]) -> None:
    from .. import models
    L, LPL, Lane = models.Library, models.links.LanePoolLink, models.Lane
    ids = [c.id for c in cards]
    libraries = dict(session.execute(
        sa.select(L.pool_id, sa.func.count()).where(L.pool_id.in_(ids)).group_by(L.pool_id)
    ).all())
    lanes: dict[int, list[int]] = defaultdict(list)
    for pool_id, number in session.execute(
        sa.select(LPL.pool_id, Lane.number).join(Lane, Lane.id == LPL.lane_id)
        .where(LPL.pool_id.in_(ids), LPL.experiment_id == obj.id).order_by(Lane.number)
    ):
        lanes[pool_id].append(number)
    for card in cards:
        card.details.append(f"{libraries.get(card.id, 0)} libraries")
        if lanes.get(card.id):
            card.details.append("lane " + ", ".join(map(str, lanes[card.id])))
        else:
            card.details.append("no lane")


def _library_details(session: Any, cards: list[Card], rows: dict[int, Any]) -> None:
    from .. import models
    pool_ids = {r.pool_id for r in rows.values() if r.pool_id is not None}
    pools = dict(session.execute(sa.select(models.Pool.id, models.Pool.name).where(models.Pool.id.in_(pool_ids))).all()) if pool_ids else {}
    for card in cards:
        row = rows[card.id]
        card.group = f"BSR_{row.seq_request_id:04d}"
        if row.pool_id is not None:
            card.details.append(f"pool {pools.get(row.pool_id, row.pool_id)}")


def build(session: Any, obj: Any, entity: Entity, limit: int = CARD_LIMIT) -> Board | None:
    """Board of the contents of `obj` (an entity with a board, see BOARDS), None otherwise."""
    if (relation := BOARDS.get(entity.name)) is None:
        return None
    child = relation.child
    model = child.model
    status_col = getattr(model, child.attr)
    id_col = getattr(model, child.id_attr)
    where = relation.where(obj)

    counts = {status: n for status, n in session.execute(sa.select(status_col, sa.func.count()).where(where).group_by(status_col))}

    extra = [model.seq_request_id, model.pool_id] if child == E.LIBRARY else []
    order = [model.seq_request_id, model.name] if child == E.LIBRARY else [model.name]
    position = sa.func.row_number().over(partition_by=status_col, order_by=order).label("position")
    inner = sa.select(id_col.label("id"), model.name.label("name"), status_col.label("status"), *extra, position).where(where).subquery()
    rows = {row.id: row for row in session.execute(sa.select(inner).where(inner.c.position <= limit).order_by(inner.c.position))}
    cards = [Card(row.id, row.name, row.status) for row in rows.values() if row.status is not None]

    _since(session, child, cards)
    if child == E.SEQ_REQUEST:
        _request_details(session, cards)
    elif child == E.POOL:
        _pool_details(session, obj, cards)
    elif child == E.LIBRARY:
        _library_details(session, cards, rows)

    by_status: dict[Any, list[Card]] = defaultdict(list)
    for card in cards:
        by_status[card.status].append(card)

    main = [s for s in child.status_enum if s.id < NORMAL_STATUS_LIMIT]
    occupied = [s for s in main if counts.get(s)]
    first = min([s.id for s in occupied] + [FIRST_COLUMN[entity.name].id])
    columns = [Column(s, by_status.get(s, []), counts.get(s, 0)) for s in main if s.id >= first]
    side = [s for s in child.status_enum if s.id >= NORMAL_STATUS_LIMIT and counts.get(s)]
    if side:
        columns.append(Column(None, [c for s in side for c in by_status.get(s, [])], sum(counts[s] for s in side)))
    return Board(relation, columns)
