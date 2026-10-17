"""Overview graphs of a request, project or experiment, drawn by static/js/overview-graph.js (React Flow).

The records behind a page as columns, left to right (e.g. samples → libraries → pools → experiments).
Each node has its status, a short subtitle, facts for its tooltip and a link to its page; edges say how
they are connected (a pool's edge to its experiment carries the pool's lanes). Samples and libraries carry a group (their pool, lab prep or request), so the graph
can bundle large sets into one node with a status breakdown and expand them on demand.

A fixed number of queries per graph: the records with their relations, library and lane read counts,
and pool sizes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import orm

from opengsync_db import SyncSession, models, categories as C
from opengsync_db.categories import ExtendedEnum

from . import responses

STATUSES: dict[str, type[ExtendedEnum]] = {
    "project": C.ProjectStatus,
    "seq_request": C.SeqRequestStatus,
    "sample": C.SampleStatus,
    "library": C.LibraryStatus,
    "pool": C.PoolStatus,
    "experiment": C.ExperimentStatus,
}

PAGES = {
    # kind: (page route, its id parameter, needs an insider)
    "project": ("project_page", "project_id", False),
    "seq_request": ("seq_request_page", "seq_request_id", False),
    "sample": ("sample_page", "sample_id", False),
    "library": ("library_page", "library_id", False),
    "pool": ("pool_page", "pool_id", False),
    "experiment": ("experiment_page", "experiment_id", True),
    "lane": ("experiment_page", "experiment_id", True),
}

_TONES = {
    # how far along a status is, for its colour: draft, waiting, progress (default), done, failed, inactive
    "DRAFT": "draft", "IDLE": "draft",
    "SUBMITTED": "waiting", "ACCEPTED": "waiting", "WAITING_DELIVERY": "waiting", "QC_PENDING": "waiting",
    "SEQUENCED": "done", "SHARED": "done", "FINISHED": "done", "DELIVERED": "done", "DEMULTIPLEXED": "done",
    "QC_COMPLETED": "done", "ARCHIVED": "done",
    "FAILED": "failed", "REJECTED": "failed",
    "REMOVED": "inactive", "REPOOLED": "inactive", "CANCELED": "inactive", "DEPLETED": "inactive",
}
_TONE_OVERRIDES = {("seq_request", "ARCHIVED"): "inactive", ("project", "ARCHIVED"): "inactive"}

_ID = 987654321
"""Placeholder id for the link templates."""


def tone(kind: str, status: ExtendedEnum) -> str:
    return _TONE_OVERRIDES.get((kind, status.name), _TONES.get(status.name, "progress"))


def reads(n: float | None) -> str | None:
    if n is None:
        return None
    for limit, unit in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if n >= limit:
            return f"{n / limit:.1f} {unit}"
    return f"{n:.0f}"


def _ranges(numbers: list[int]) -> str:
    """1, 2, 3, 5 → "1–3, 5"."""
    out: list[str] = []
    for n in numbers:
        if out and n == int(out[-1].split("–")[-1]) + 1:
            out[-1] = f"{out[-1].split('–')[0]}–{n}"
        else:
            out.append(str(n))
    return ", ".join(out)


def _num(value: float | None, unit: str, digits: int = 1) -> str | None:
    return None if value is None else f"{value:.{digits}f} {unit}"


class Graph:
    def __init__(self, columns: Iterable[tuple[str, str]], insider: bool):
        self.columns = list(columns)
        self.insider = insider
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str], dict[str, Any]] = {}
        self.groups: dict[str, str] = {}

    def add(
        self, kind: str, obj_id: int, label: str, *,
        status: ExtendedEnum | None = None, sub: str | None = None, group: tuple[str, str] | None = None,
        facts: Iterable[tuple[str, str | None]] = (), metrics: dict[str, float] | None = None,
        link_id: int | None = None,
    ) -> str:
        node_id = f"{kind}-{obj_id}"
        if node_id in self.nodes:
            return node_id
        node: dict[str, Any] = {"id": node_id, "kind": kind, "ref": link_id if link_id is not None else obj_id, "label": label}
        if status is not None:
            node["status"] = status.id
        if sub:
            node["sub"] = sub
        if group is not None:
            node["group"] = group[0]
            self.groups.setdefault(group[0], group[1])
        if facts := [[name, value] for name, value in facts if value not in (None, "")]:
            node["facts"] = facts
        if metrics := {k: v for k, v in (metrics or {}).items() if v is not None}:
            node["metrics"] = metrics
        self.nodes[node_id] = node
        return node_id

    def link(self, source: str, target: str, *, label: str | None = None, lanes: list[int] | None = None) -> None:
        """`lanes`: of a pool on its experiment, shown as badges on the edge."""
        extra: dict[str, Any] = {}
        if label:
            extra["label"] = label
        if lanes:
            extra["lanes"] = lanes
        self.edges.setdefault((source, target), extra)

    def to_json(self) -> dict[str, Any]:
        used = {node["kind"] for node in self.nodes.values()}
        links = {}
        for kind, (page, param, insider_only) in PAGES.items():
            if kind in used and (self.insider or not insider_only):
                links[kind] = str(responses.url_for(page, **{param: _ID})).replace(str(_ID), "{id}")
        return {
            "columns": [{"kind": kind, "label": label} for kind, label in self.columns if kind in used],
            "statuses": {
                kind: {str(s.id): {"label": s.label, "icon": getattr(s, "icon", ""), "tone": tone(kind, s)} for s in enum.as_list()}
                for kind, enum in STATUSES.items() if kind in used
            },
            "links": links,
            "groups": self.groups,
            "nodes": list(self.nodes.values()),
            "edges": [{"source": s, "target": t, **extra} for (s, t), extra in self.edges.items()],
        }


# ── shared pieces ──────────────────────────────────────────────────────────────────────────────────

def _library_reads(session: SyncSession, library_ids: list[int], experiment_id: int | None = None) -> dict[int, int]:
    if not library_ids:
        return {}
    query = (
        sa.select(models.SeqQuality.library_id, sa.func.sum(models.SeqQuality.num_reads))
        .where(models.SeqQuality.library_id.in_(library_ids))
        .group_by(models.SeqQuality.library_id)
    )
    if experiment_id is not None:
        query = query.where(models.SeqQuality.experiment_id == experiment_id)
    return {library_id: int(n) for library_id, n in session.execute(query)}


def _pool_sizes(session: SyncSession, pool_ids: Iterable[int]) -> dict[int, int]:
    if not (pool_ids := list(pool_ids)):
        return {}
    return dict(session.execute(  # type: ignore[arg-type]
        sa.select(models.Library.pool_id, sa.func.count()).where(models.Library.pool_id.in_(pool_ids)).group_by(models.Library.pool_id)
    ).all())


def _library_group(library: models.Library, with_request: bool, insider: bool) -> tuple[str, str]:
    request = f"{library.seq_request.identifier} · " if with_request else ""
    key = f"r{library.seq_request_id}-"
    if library.pool is not None:
        return key + f"pool-{library.pool_id}", f"{request}pool {library.pool.name}"
    if library.lab_prep is not None and insider:
        return key + f"prep-{library.lab_prep_id}", f"{request}prep {library.lab_prep.identifier}"
    return key + "none", f"{request}not pooled"


def _add_library(g: Graph, library: models.Library, read_count: int | None, group: tuple[str, str]) -> str:
    requested = library.seq_depth_requested
    return g.add(
        "library", library.id, library.name, status=library.status, sub=library.type.abbreviation, group=group,
        facts=[
            ("Type", library.type.label),
            ("Genome", library.genome_ref.label),
            ("Request", library.seq_request.identifier),
            ("Lab prep", library.lab_prep.identifier if library.lab_prep is not None and g.insider else None),
            ("Pool", library.pool.name if library.pool is not None else None),
            ("Qubit", _num(library.qubit_concentration, "ng/µl", 2)),
            ("Fragment size", _num(library.avg_fragment_size, "bp", 0)),
            ("Reads", reads(read_count)),
            ("Requested", f"{reads(requested * 1e6)} reads" if requested else None),
        ],
        metrics={"reads": read_count, "requested": requested * 1e6 if requested else None},
    )


def _add_pool(g: Graph, pool: models.Pool, size: int | None) -> str:
    lanes = sorted(link.lane_num for link in pool.lane_links)
    sub = f"{size} {'library' if size == 1 else 'libraries'}" if size is not None else pool.type.label
    return g.add(
        "pool", pool.id, pool.name, status=pool.status, sub=sub,
        facts=[
            ("Type", pool.type.label),
            ("Libraries", str(size) if size is not None else None),
            ("Qubit", _num(pool.qubit_concentration, "ng/µl", 2)),
            ("Fragment size", _num(pool.avg_fragment_size, "bp", 0)),
            ("Molarity", _num(pool.molarity, "nM", 2)),
            ("Requested", f"{reads(pool.num_m_reads_requested * 1e6)} reads" if pool.num_m_reads_requested else None),
            ("Experiment", pool.experiment.name if pool.experiment is not None else None),
            ("Lanes", _ranges(lanes) if lanes else None),
            ("Per lane", ", ".join(f"lane {link.lane_num}: {link.num_m_reads:g} M" for link in sorted(pool.lane_links, key=lambda link: link.lane_num) if link.num_m_reads)),
        ],
    )


def _add_experiment(g: Graph, experiment: models.Experiment) -> str:
    run = experiment.seq_run
    return g.add(
        "experiment", experiment.id, experiment.name, status=experiment.status, sub=experiment.workflow.label,
        facts=[
            ("Workflow", experiment.workflow.label),
            ("Run", f"{run.status.label} {run.status.icon}" if run is not None else None),
            ("Flowcell", run.flowcell_id if run is not None else None),
        ],
    )


def _add_downstream(g: Graph, libraries: list[models.Library], read_counts: dict[int, int], pool_sizes: dict[int, int], with_request: bool) -> dict[int, str]:
    """Libraries, their pools and the pools' experiments; returns the library nodes."""
    nodes = {}
    for library in libraries:
        group = _library_group(library, with_request, g.insider)
        nodes[library.id] = _add_library(g, library, read_counts.get(library.id), group)
        if (pool := library.pool) is None:
            continue
        pool_node = _add_pool(g, pool, pool_sizes.get(pool.id))
        g.link(nodes[library.id], pool_node)
        if pool.experiment is not None:
            lanes = sorted(link.lane_num for link in pool.lane_links if link.experiment_id == pool.experiment_id)
            g.link(pool_node, _add_experiment(g, pool.experiment), lanes=lanes)
    return nodes


def _add_sample(g: Graph, sample: models.Sample, group: tuple[str, str], shown: int | None = None) -> str:
    """`shown`: how many of the sample's libraries the graph shows, when not all of them (e.g. those of one request)."""
    total = len(sample.library_links)
    noun = "library" if total == 1 else "libraries"
    if shown is None:
        sub, libraries = f"{total} {noun}", str(total)
    else:
        sub, libraries = f"{shown}/{total} {noun}", f"{shown} in this request, {total} in total"
    return g.add(
        "sample", sample.id, sample.name, status=sample.status, group=group, sub=sub,
        facts=[
            ("Project", sample.project.identifier_display),
            ("Libraries", libraries),
            ("Qubit", _num(sample.qubit_concentration, "ng/µl", 2)),
            ("Fragment size", _num(sample.avg_fragment_size, "bp", 0)),
        ],
    )


def _library_options() -> list:
    return [
        orm.selectinload(models.Library.seq_request),
        orm.selectinload(models.Library.lab_prep),
        orm.selectinload(models.Library.pool).options(
            orm.selectinload(models.Pool.experiment),
            orm.selectinload(models.Pool.lane_links),
        ),
    ]


# ── the three overviews ────────────────────────────────────────────────────────────────────────────

def seq_request_graph(session: SyncSession, seq_request_id: int, insider: bool) -> dict[str, Any]:
    """Projects → samples → libraries → pools → experiments of a request."""
    libraries = session.scalars(
        sa.select(models.Library).where(models.Library.seq_request_id == seq_request_id)
        .options(
            *_library_options(),
            orm.selectinload(models.Library.sample_links).selectinload(models.links.SampleLibraryLink.sample).options(
                orm.selectinload(models.Sample.project), orm.selectinload(models.Sample.library_links),
            ),
        )
        .order_by(models.Library.name, models.Library.id)
    ).all()
    g = Graph([("project", "Projects"), ("sample", "Samples"), ("library", "Libraries"), ("pool", "Pools"), ("experiment", "Experiments")], insider)
    library_nodes = _add_downstream(
        g, list(libraries), _library_reads(session, [lib.id for lib in libraries]),
        _pool_sizes(session, {lib.pool_id for lib in libraries if lib.pool_id is not None}), with_request=False,
    )
    shown = Counter(link.sample_id for library in libraries for link in library.sample_links)
    for library in libraries:
        for link in sorted(library.sample_links, key=lambda link: link.sample.name):
            sample = link.sample
            sample_node = _add_sample(g, sample, _library_group(library, False, insider), shown=shown[sample.id])
            g.link(sample_node, library_nodes[library.id])
            project = sample.project
            project_node = g.add(
                "project", project.id, project.title, status=project.status, sub=project.identifier_display,
                facts=[("Identifier", project.identifier_display)],
            )
            g.link(project_node, sample_node)
    return g.to_json()


def project_graph(session: SyncSession, project_id: int, insider: bool) -> dict[str, Any]:
    """Samples → libraries → pools → experiments of a project; libraries are grouped by request and pool."""
    samples = session.scalars(
        sa.select(models.Sample).where(models.Sample.project_id == project_id)
        .options(
            orm.selectinload(models.Sample.project),
            orm.selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library).options(*_library_options()),
        )
        .order_by(models.Sample.name, models.Sample.id)
    ).all()
    libraries = {link.library.id: link.library for sample in samples for link in sample.library_links}
    ordered = sorted(libraries.values(), key=lambda lib: (lib.seq_request_id, lib.pool_id or 0, lib.name))
    g = Graph([("sample", "Samples"), ("library", "Libraries"), ("pool", "Pools"), ("experiment", "Experiments")], insider)
    library_nodes = _add_downstream(
        g, ordered, _library_reads(session, list(libraries)),
        _pool_sizes(session, {lib.pool_id for lib in ordered if lib.pool_id is not None}), with_request=True,
    )
    for sample in samples:
        links = sorted(sample.library_links, key=lambda link: (link.library.seq_request_id, link.library.name))
        group = _library_group(links[0].library, True, insider) if links else ("none", "no libraries")
        sample_node = _add_sample(g, sample, group)
        for link in links:
            g.link(sample_node, library_nodes[link.library_id])
    return g.to_json()


def experiment_graph(session: SyncSession, experiment_id: int) -> dict[str, Any]:
    """Requests → libraries → pools → lanes of an experiment (insiders only)."""
    experiment = session.get_one(sa.select(models.Experiment).where(models.Experiment.id == experiment_id).options(orm.selectinload(models.Experiment.lanes)))
    libraries = session.scalars(
        sa.select(models.Library).join(models.Pool, models.Pool.id == models.Library.pool_id)
        .where(models.Pool.experiment_id == experiment_id)
        .options(*_library_options())
        .order_by(models.Library.seq_request_id, models.Library.pool_id, models.Library.name)
    ).all()
    lane_reads = {lane: int(n) for lane, n in session.execute(
        sa.select(models.SeqQuality.lane, sa.func.sum(models.SeqQuality.num_reads))
        .where(models.SeqQuality.experiment_id == experiment_id).group_by(models.SeqQuality.lane)
    )}
    g = Graph([("seq_request", "Requests"), ("library", "Libraries"), ("pool", "Pools"), ("lane", "Lanes")], insider=True)
    read_counts = _library_reads(session, [lib.id for lib in libraries], experiment_id)
    pool_sizes = _pool_sizes(session, {lib.pool_id for lib in libraries if lib.pool_id is not None})
    lane_pools: dict[int, dict[int, float | None]] = defaultdict(dict)
    for library in libraries:
        assert library.pool is not None
        for link in library.pool.lane_links:
            if link.experiment_id == experiment_id:
                lane_pools[link.lane_num][library.pool.id] = link.num_m_reads
    lanes = {}
    for lane in experiment.lanes:
        pools = lane_pools.get(lane.number, {})
        requested = sum(m for m in pools.values() if m)
        sub = [f"{len(pools)} {'pool' if len(pools) == 1 else 'pools'}"]
        if lane_reads.get(lane.number):
            sub.append(f"{reads(lane_reads[lane.number])} reads")
        elif requested:
            sub.append(f"{requested:g} M requested")
        lanes[lane.number] = g.add(
            "lane", lane.id, f"Lane {lane.number}", link_id=experiment.id, sub=" · ".join(sub),
            facts=[
                ("Pools", str(len(pools))),
                ("Requested", f"{requested:g} M reads" if requested else None),
                ("Reads", reads(lane_reads.get(lane.number))),
                ("PhiX", _num(lane.phi_x, "%")),
                ("Loading conc.", _num(lane.sequencing_qubit_concentration, "ng/µl", 2)),
                ("Target molarity", _num(lane.target_molarity, "nM", 2)),
            ],
        )
    for library in libraries:
        request = library.seq_request
        request_node = g.add(
            "seq_request", request.id, request.name, status=request.status, sub=request.identifier,
            facts=[("Identifier", request.identifier), ("Submission", request.submission_type.label)],
        )
        library_node = _add_library(g, library, read_counts.get(library.id), _library_group(library, True, True))
        g.link(request_node, library_node)
        pool = library.pool
        assert pool is not None
        pool_node = _add_pool(g, pool, pool_sizes.get(pool.id))
        g.link(library_node, pool_node)
        for link in pool.lane_links:
            if link.experiment_id == experiment_id and link.lane_num in lanes:
                g.link(pool_node, lanes[link.lane_num])
    return g.to_json()
