"""Free-text search across the main entities (navbar search).

Matching is tiered so literal hits outrank fuzzy ones, which matters for names full of
separators and special characters:

    1.0  exact (case-insensitive)
    0.9  prefix
    0.8  substring, wildcards escaped
    0.7  substring after stripping separators (utils.compact_key), separator-heavy names only
  <=0.6  pg_trgm word_similarity, for typos

Every filter is backed by a `lower(col) gin_trgm_ops` (or compact-key) index. Fuzzy matching uses
the `%>` operator, so call `threshold_statement()` in the same transaction before `search()`.
"""

import re
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import orm

from ..models import SeqRequest, Project, Experiment, LabPrep, Pool, Sample, Library, User, Group, Kit, Protocol
from ..categories import KitType, GroupType, ServiceType
from ..core import utils

KINDS = (
    "seq_request", "project", "experiment", "lab_prep", "pool", "sample", "library",
    "user", "group", "index_kit", "library_kit", "feature_kit", "protocol",
)

MIN_QUERY_LENGTH = 2
# Below this, trigram substring and fuzzy matching are mostly noise; only exact and prefix are used.
MIN_FUZZY_LENGTH = 3
MAX_QUERY_LENGTH = 128
WORD_SIMILARITY_THRESHOLD = 0.4

_SEQ_REQUEST_ID = re.compile(r"^bsr[\s_-]*(\d+)$")


@dataclass(frozen=True)
class SearchQuery:
    text: str
    compact: str
    seq_request_digits: str | None

    @classmethod
    def parse(cls, raw: str | None) -> "SearchQuery | None":
        """Normalize user input; returns None when it is too short to search."""
        text = " ".join((raw or "").lower().split())[:MAX_QUERY_LENGTH]
        if len(text) < MIN_QUERY_LENGTH:
            return None
        match = _SEQ_REQUEST_ID.match(text)
        return cls(
            text=text,
            compact=re.sub(r"[^a-z0-9]+", "", text),
            # more digits than fit an integer id cannot match and would overflow the comparison
            seq_request_digits=match.group(1) if match and len(match.group(1)) <= 9 else None,
        )

    @property
    def fuzzy(self) -> bool:
        return len(self.text) >= MIN_FUZZY_LENGTH

    @property
    def is_email(self) -> bool:
        return "@" in self.text


def threshold_statement(threshold: float = WORD_SIMILARITY_THRESHOLD) -> sa.Select:
    """Transaction-local threshold for the `%>` operator (the default of 0.6 misses most typos)."""
    return sa.select(sa.func.set_config("pg_trgm.word_similarity_threshold", str(threshold), True))


_Match = tuple[sa.ColumnElement[bool], sa.ColumnElement[float]]


def _match(column, query: SearchQuery, compact: bool = False) -> _Match:
    """(filter, score) for one text column; see the module docstring for the tiers."""
    col = sa.func.lower(column)
    escaped = utils.escape_like(query.text)
    prefix = col.like(f"{escaped}%", escape="\\")
    tiers: list[tuple[sa.ColumnElement[bool], float]] = [(col == query.text, 1.0), (prefix, 0.9)]
    filters: list[sa.ColumnElement[bool]] = [prefix]
    fallback: sa.ColumnElement[float] = sa.literal(0.0)

    if query.fuzzy:
        substring = col.like(f"%{escaped}%", escape="\\")
        filters = [substring, col.op("%>")(query.text)]
        tiers.append((substring, 0.8))
        if compact and len(query.compact) >= MIN_FUZZY_LENGTH:
            # compact only contains [a-z0-9], so it needs no escaping
            compact_substring = utils.compact_key(column).like(f"%{query.compact}%")
            filters.append(compact_substring)
            tiers.append((compact_substring, 0.7))
        fallback = 0.6 * sa.func.word_similarity(query.text, col)

    return sa.or_(*filters), sa.case(*tiers, else_=fallback)


# A match on the owner's name ranks just below an equally good match on the item itself.
PERSON_WEIGHT = 0.9


def _weighted(match: _Match, weight: float) -> _Match:
    return match[0], match[1] * weight


def _full_name(user) -> sa.ColumnElement[str]:
    # literal ' ' so the expression matches trgm_lims_user_full_name_idx
    return user.first_name + sa.literal_column("' '", sa.String) + user.last_name


def _seq_request_number(id_column) -> sa.ColumnElement[str]:
    """Zero-padded id as in SeqRequest.identifier; lpad alone would truncate ids > 9999."""
    id_text = sa.cast(id_column, sa.Text)
    return sa.func.lpad(id_text, sa.func.greatest(4, sa.func.length(id_text)), "0")


def _seq_request_identifier(id_column) -> sa.ColumnElement[str]:
    return sa.literal_column("'BSR_'", sa.String) + _seq_request_number(id_column)


def _enum_label(enum_column, enum) -> sa.ColumnElement[str]:
    # compare the stored ids: the EnumColumn bind processor would expect enum members
    raw = sa.type_coerce(enum_column, sa.SmallInteger)
    return sa.cast(sa.case({e.id: e.label for e in enum.as_list()}, value=raw), sa.Text)


def _ranked(
    kind: str, from_, id_column, label, matches: list[_Match], limit: int,
    code=None, detail=None, where: sa.ColumnElement[bool] | None = None,
) -> sa.Subquery:
    score = matches[0][1] if len(matches) == 1 else sa.func.greatest(*(m[1] for m in matches))
    statement = (
        sa.select(
            sa.literal_column(f"'{kind}'", sa.Text).label("kind"),
            id_column.label("id"),
            sa.cast(code if code is not None else sa.null(), sa.Text).label("code"),
            sa.cast(label, sa.Text).label("label"),
            sa.cast(detail if detail is not None else sa.null(), sa.Text).label("detail"),
            score.label("score"),
            sa.func.count().over().label("total"),
        )
        .select_from(from_)
        .where(sa.or_(*(m[0] for m in matches)))
    )
    if where is not None:
        statement = statement.where(where)
    return statement.order_by(sa.desc("score"), id_column.desc()).limit(limit).subquery(f"search_{kind}")


def _seq_requests(query: SearchQuery, limit: int) -> sa.Subquery:
    requestor = orm.aliased(User)
    matches = [_match(SeqRequest.name, query), _weighted(_match(_full_name(requestor), query), PERSON_WEIGHT)]
    if (digits := query.seq_request_digits) is not None:
        # typing "BSR_0012" passes through "bsr_001": exact id first, then ids whose padded form starts with it
        matches.append((
            sa.or_(SeqRequest.id == int(digits), _seq_request_number(SeqRequest.id).like(f"{digits}%")),
            sa.case((SeqRequest.id == int(digits), 1.0), else_=0.9),
        ))
    return _ranked(
        "seq_request", orm.join(SeqRequest, requestor, requestor.id == SeqRequest.requestor_id),
        SeqRequest.id, SeqRequest.name, matches, limit,
        code=_seq_request_identifier(SeqRequest.id), detail=_full_name(requestor),
    )


def _projects(query: SearchQuery, limit: int) -> sa.Subquery:
    owner = orm.aliased(User)
    return _ranked(
        "project", orm.join(Project, owner, owner.id == Project.owner_id), Project.id, Project.title,
        [
            _match(Project.identifier, query), _match(Project.title, query),
            _weighted(_match(_full_name(owner), query), PERSON_WEIGHT),
        ],
        limit, code=Project.identifier, detail=_full_name(owner),
    )


def _experiments(query: SearchQuery, limit: int) -> sa.Subquery:
    operator = orm.aliased(User)
    return _ranked(
        "experiment", orm.join(Experiment, operator, operator.id == Experiment.operator_id),
        Experiment.id, Experiment.name, [_match(Experiment.name, query, compact=True)], limit,
        detail=_full_name(operator),
    )


def _lab_preps(query: SearchQuery, limit: int) -> sa.Subquery:
    creator = orm.aliased(User)
    return _ranked(
        "lab_prep", orm.join(LabPrep, creator, creator.id == LabPrep.creator_id),
        LabPrep.id, LabPrep.name, [_match(LabPrep.name, query, compact=True)], limit,
        detail=_full_name(creator),
    )


def _pools(query: SearchQuery, limit: int) -> sa.Subquery:
    owner = orm.aliased(User)
    return _ranked(
        "pool", orm.join(Pool, owner, owner.id == Pool.owner_id),
        Pool.id, Pool.name, [_match(Pool.name, query, compact=True)], limit,
        detail=_full_name(owner),
    )


def _samples(query: SearchQuery, limit: int) -> sa.Subquery:
    return _ranked(
        "sample", orm.join(Sample, Project, Project.id == Sample.project_id),
        Sample.id, Sample.name, [_match(Sample.name, query, compact=True)], limit,
        detail=sa.func.coalesce(Project.identifier, Project.title),
    )


def _libraries(query: SearchQuery, limit: int) -> sa.Subquery:
    return _ranked(
        "library", Library, Library.id, Library.name,
        [_match(Library.name, query, compact=True), _match(Library.sample_name, query, compact=True)], limit,
        # the sample name shows why a library matched when only its sample_name did
        detail=Library.sample_name + sa.literal_column("' · '", sa.String) + _seq_request_identifier(Library.seq_request_id),
    )


def _users(query: SearchQuery, limit: int) -> sa.Subquery:
    return _ranked(
        "user", User, User.id, _full_name(User),
        [_match(_full_name(User), query), _match(User.email, query)], limit, detail=User.email,
    )


def _groups(query: SearchQuery, limit: int) -> sa.Subquery:
    return _ranked(
        "group", Group, Group.id, Group.name, [_match(Group.name, query)], limit,
        detail=_enum_label(Group.type, GroupType),
    )


def _kits(kit_type: KitType, kind: str):
    def branch(query: SearchQuery, limit: int) -> sa.Subquery:
        return _ranked(
            kind, Kit, Kit.id, Kit.name, [_match(Kit.identifier, query), _match(Kit.name, query)], limit,
            code=Kit.identifier, where=Kit.kit_type == kit_type,
        )
    return branch


def _protocols(query: SearchQuery, limit: int) -> sa.Subquery:
    return _ranked(
        "protocol", Protocol, Protocol.id, Protocol.name, [_match(Protocol.name, query)], limit,
        detail=_enum_label(Protocol.service_type, ServiceType),
    )


_BRANCHES = {
    "seq_request": _seq_requests,
    "project": _projects,
    "experiment": _experiments,
    "lab_prep": _lab_preps,
    "pool": _pools,
    "sample": _samples,
    "library": _libraries,
    "user": _users,
    "group": _groups,
    "index_kit": _kits(KitType.INDEX_KIT, "index_kit"),
    "library_kit": _kits(KitType.LIBRARY_KIT, "library_kit"),
    "feature_kit": _kits(KitType.FEATURE_KIT, "feature_kit"),
    "protocol": _protocols,
}
assert set(_BRANCHES) == set(KINDS)


def search(query: SearchQuery, kinds: list[str] | None = None, limit_per_kind: int = 5) -> sa.CompoundSelect | sa.Select:
    """Top matches per kind as rows of (kind, id, code, label, detail, score, total).

    `total` is the number of matches of that kind before the limit. An email-like query only
    searches users.
    """
    if kinds is None:
        kinds = list(KINDS)
    if unknown := set(kinds) - set(KINDS):
        raise ValueError(f"Unknown search kinds: {sorted(unknown)}")
    if query.is_email and len(kinds) > 1:
        kinds = [kind for kind in kinds if kind == "user"] or kinds

    branches = [sa.select(*_BRANCHES[kind](query, limit_per_kind).c) for kind in kinds]
    return branches[0] if len(branches) == 1 else sa.union_all(*branches)
