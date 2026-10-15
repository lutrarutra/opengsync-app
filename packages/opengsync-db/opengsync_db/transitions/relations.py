"""Child relations that rules aggregate over.

Each relation is a WHERE clause on the child model, so rules can count children per status in one
`GROUP BY` instead of loading them. The definitions mirror the joins the legacy code uses
(e.g. project libraries via sample links, like `Project.libraries` and the status worker).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import sqlalchemy as sa

from .core import Entity
from . import entities as E


@dataclass(frozen=True)
class Relation:
    name: str
    parent: Entity
    child: Entity
    where: Callable[[Any], sa.ColumnElement[bool]]
    """Builds the filter on the child model for one parent object."""
    label: str

    def __repr__(self) -> str:
        return f"Relation[{self.parent.name}.{self.name}]"


def _m():
    from .. import models
    return models


def _request_libraries(req) -> sa.ColumnElement[bool]:
    return _m().Library.seq_request_id == req.id


def _request_samples(req) -> sa.ColumnElement[bool]:
    m = _m()
    return m.Sample.id.in_(
        sa.select(m.links.SampleLibraryLink.sample_id)
        .join(m.Library, m.Library.id == m.links.SampleLibraryLink.library_id)
        .where(m.Library.seq_request_id == req.id)
    )


def _request_pools(req) -> sa.ColumnElement[bool]:
    m = _m()
    return sa.or_(
        m.Pool.seq_request_id == req.id,
        m.Pool.id.in_(sa.select(m.Library.pool_id).where(m.Library.seq_request_id == req.id)),
    )


def _project_libraries(project) -> sa.ColumnElement[bool]:
    m = _m()
    return m.Library.id.in_(
        sa.select(m.links.SampleLibraryLink.library_id)
        .join(m.Sample, m.Sample.id == m.links.SampleLibraryLink.sample_id)
        .where(m.Sample.project_id == project.id)
    )


def _project_requests(project) -> sa.ColumnElement[bool]:
    m = _m()
    return m.SeqRequest.id.in_(
        sa.select(m.Library.seq_request_id)
        .join(m.links.SampleLibraryLink, m.links.SampleLibraryLink.library_id == m.Library.id)
        .join(m.Sample, m.Sample.id == m.links.SampleLibraryLink.sample_id)
        .where(m.Sample.project_id == project.id)
    )


REQUEST_LIBRARIES = Relation("libraries", E.SEQ_REQUEST, E.LIBRARY, _request_libraries, "libraries of the request")
REQUEST_SAMPLES = Relation("samples", E.SEQ_REQUEST, E.SAMPLE, _request_samples, "samples of the request")
REQUEST_POOLS = Relation("pools", E.SEQ_REQUEST, E.POOL, _request_pools, "pools of the request or its libraries")
REQUEST_LIBRARY_POOLS = Relation(
    "library_pools", E.SEQ_REQUEST, E.POOL,
    lambda req: _m().Pool.id.in_(sa.select(_m().Library.pool_id).where(_m().Library.seq_request_id == req.id)),
    "pools of the request's libraries",
)
REQUEST_LAB_PREPS = Relation(
    "lab_preps", E.SEQ_REQUEST, E.LAB_PREP,
    lambda req: _m().LabPrep.id.in_(sa.select(_m().Library.lab_prep_id).where(_m().Library.seq_request_id == req.id)),
    "lab preps of the request's libraries",
)
REQUEST_EXPERIMENTS = Relation(
    "experiments", E.SEQ_REQUEST, E.EXPERIMENT,
    lambda req: _m().Experiment.id.in_(sa.select(_m().Library.experiment_id).where(_m().Library.seq_request_id == req.id)),
    "experiments of the request's libraries",
)
PROJECT_LIBRARIES = Relation("libraries", E.PROJECT, E.LIBRARY, _project_libraries, "libraries of the project")
PROJECT_SAMPLES = Relation("samples", E.PROJECT, E.SAMPLE, lambda p: _m().Sample.project_id == p.id, "samples of the project")
PROJECT_REQUESTS = Relation("seq_requests", E.PROJECT, E.SEQ_REQUEST, _project_requests, "requests of the project")
PREP_LIBRARIES = Relation("libraries", E.LAB_PREP, E.LIBRARY, lambda p: _m().Library.lab_prep_id == p.id, "libraries of the lab prep")
PREP_POOLS = Relation("pools", E.LAB_PREP, E.POOL, lambda p: _m().Pool.lab_prep_id == p.id, "pools of the lab prep")
EXPERIMENT_POOLS = Relation("pools", E.EXPERIMENT, E.POOL, lambda x: _m().Pool.experiment_id == x.id, "pools of the experiment")
EXPERIMENT_LIBRARIES = Relation("libraries", E.EXPERIMENT, E.LIBRARY, lambda x: _m().Library.experiment_id == x.id, "libraries of the experiment")
POOL_LIBRARIES = Relation("libraries", E.POOL, E.LIBRARY, lambda p: _m().Library.pool_id == p.id, "libraries of the pool")

RELATIONS: tuple[Relation, ...] = (
    REQUEST_LIBRARIES, REQUEST_SAMPLES, REQUEST_POOLS, REQUEST_LIBRARY_POOLS, REQUEST_LAB_PREPS, REQUEST_EXPERIMENTS,
    PROJECT_LIBRARIES, PROJECT_SAMPLES, PROJECT_REQUESTS,
    PREP_LIBRARIES, PREP_POOLS,
    EXPERIMENT_POOLS, EXPERIMENT_LIBRARIES,
    POOL_LIBRARIES,
)
