"""The search box of a table: parsing and SQL.

Syntax (also in docs/tables.md):

    pbmc               any searchable field (names, joined owner/group/project, ...)
    pbmc d04           both terms must match (each in any field)
    "liver organoid"   quotes keep spaces in one term
    owner:chen         only the field ``owner``
    group:"Immuno Lab" field with a quoted value
    #1291  or  1291    that id first, then names etc. containing the digits (id:1291 for the id only)
    status:pooled      a filter field in the box: matches members whose label starts with the text

Terms are AND-ed; within a term the fields are OR-ed. Matching is literal first; only when that finds
nothing, the table's own text columns also match with typo tolerance. Ranking reuses the tiers of the navbar
search (opengsync_db.queries.search): exact 1.0 > prefix 0.9 > substring 0.8 > compact 0.7 > fuzzy <= 0.6.
Fields reached through a relationship path (owner, group, project, ...) match literally (substring) and
count with a fixed weight, since their score cannot be computed inside the EXISTS.
"""
import re
from dataclasses import dataclass
from typing import Sequence

import sqlalchemy as sa

from opengsync_db import queries as Q
from opengsync_db.core import utils

from .spec import Col, Exact, Text, Enum, through

_TERM = re.compile(r'(?:([A-Za-z_][\w]*):)?(?:"([^"]*)"?|(\S+))')
_ID = re.compile(r"^#?(\d{1,9})$")
JOINED_SCORE = 0.75
ID_BOOST = 2.0  # an exact id outranks every text tier (<= 1.0)


@dataclass(frozen=True)
class Term:
    field: str | None
    text: str


def parse_terms(q: str, fields: Sequence[str]) -> list[Term]:
    """Split the search box into terms; ``field:`` prefixes only count for known fields."""
    known = {f.lower(): f for f in fields}
    terms: list[Term] = []
    for match in _TERM.finditer(q or ""):
        prefix, quoted, bare = match.group(1), match.group(2), match.group(3)
        text = (quoted if quoted is not None else bare or "").strip()
        if prefix is not None and prefix.lower() not in known:
            # not a field: the whole token is text (e.g. "10:30" or "a:b")
            text = f"{prefix}:{text}" if text else prefix
            prefix = None
        if not text:
            continue
        terms.append(Term(field=known[prefix.lower()] if prefix else None, text=text))
    return terms


def _text_match(search: Text, text: str, fuzzy: bool) -> tuple[sa.ColumnElement[bool], sa.ColumnElement[float]] | None:
    if (query := Q.search.SearchQuery.parse(text)) is None:
        return None
    escaped = utils.escape_like(query.text)
    if search.via:
        # joined fields only match literally: typo tolerance on owners, projects and requests is mostly noise
        clause = through(search.via, sa.or_(*(sa.func.lower(c).like(f"%{escaped}%", escape="\\") for c in search.columns)))
        return clause, sa.case((clause, JOINED_SCORE * search.weight), else_=0.0)

    if fuzzy:
        if not query.fuzzy:
            return None
        matches = [Q.search.match(column, query, compact=search.compact) for column in search.columns]
    else:
        # literal tiers of the navbar search (exact > prefix > substring > compact), also for 2-character terms
        matches = []
        for column in search.columns:
            col = sa.func.lower(column)
            tiers = [
                (col == query.text, 1.0),
                (col.like(f"{escaped}%", escape="\\"), 0.9),
                (col.like(f"%{escaped}%", escape="\\"), 0.8),
            ]
            if search.compact and len(query.compact) >= Q.search.MIN_FUZZY_LENGTH:
                tiers.append((utils.compact_key(column).like(f"%{query.compact}%"), 0.7))
            matches.append((sa.or_(*(t[0] for t in tiers[1:])), sa.case(*tiers, else_=0.0)))
    clause = sa.or_(*(m[0] for m in matches))
    score = matches[0][1] if len(matches) == 1 else sa.func.greatest(*(m[1] for m in matches))
    return clause, score * search.weight


def _field_match(
    col: Col, text: str, model: type, targeted: bool, fuzzy: bool,
) -> tuple[sa.ColumnElement[bool], sa.ColumnElement[float]] | None:
    search = col.search
    if isinstance(search, Exact):
        text = text.strip()
        for prefix in search.prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].lstrip("_- ")
                break
        if (m := _ID.match(text)) is None:
            return None
        clause = search.column == int(m.group(1))
        return clause, sa.case((clause, 1.0), else_=0.0)
    if isinstance(search, Text):
        return _text_match(search, text.lstrip("#") if text.startswith("#") and len(text) > 1 else text, fuzzy)
    if targeted and isinstance(col.filter, Enum):
        members = col.filter.find(text)
        column = col.filter.column if col.filter.column is not None else getattr(model, col.key)
        clause = through(col.filter.via, column.in_(members)) if members else sa.false()
        return clause, sa.case((clause, 1.0), else_=0.0)
    return None


def search(
    q: str, columns: Sequence[Col], model: type, scope: str | None = None, fuzzy: bool = False,
) -> tuple[list[sa.ColumnElement[bool]], sa.ColumnElement[float] | None]:
    """WHERE clauses (AND-ed) and a relevance score for the search box, ``([], None)`` without a search.

    ``fuzzy`` adds pg_trgm typo tolerance to the table's own text columns (exact and literal matches still rank
    first); Table.render only uses it when the literal search finds nothing, so "d01" does not also list "d02"."""
    by_key = {c.key: c for c in columns}
    addressable = [c.key for c in columns if c.searchable or isinstance(c.filter, Enum)]
    clauses: list[sa.ColumnElement[bool]] = []
    scores: list[sa.ColumnElement[float]] = []

    for term in parse_terms(q, addressable):
        if term.field is not None:
            candidates, targeted = [by_key[term.field]], True
        elif scope is not None:
            candidates, targeted = [by_key[scope]], True
        else:
            candidates, targeted = [c for c in columns if c.searchable], False

        matches = []
        for c in candidates:
            if (m := _field_match(c, term.text, model, targeted, fuzzy)) is None:
                continue
            if isinstance(c.search, Exact):
                # the row with exactly this id comes first, before names that merely contain the digits
                m = (m[0], m[1] * ID_BOOST)
            matches.append(m)
        if not matches:
            if targeted or _ID.match(term.text) is None and len(term.text) >= Q.search.MIN_QUERY_LENGTH:
                # a term that can match nothing (e.g. id:abc) hides everything rather than being ignored
                clauses.append(sa.false())
            continue

        clauses.append(sa.or_(*(m[0] for m in matches)))
        scores.append(matches[0][1] if len(matches) == 1 else sa.func.greatest(*(m[1] for m in matches)))

    if not scores:
        return clauses, None
    total = scores[0]
    for score in scores[1:]:
        total = total + score
    return clauses, total
