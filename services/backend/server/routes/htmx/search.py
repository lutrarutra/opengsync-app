from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from markupsafe import Markup, escape

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, responses, exceptions as exc
from ...core.search import SEARCH_KINDS, SearchKind

router = APIRouter(prefix="/search", tags=["search"])

PER_KIND_LIMIT = 5
SINGLE_KIND_LIMIT = 20


@dataclass
class SearchHit:
    url: str
    code: Markup | None
    label: Markup
    detail: str | None


@dataclass
class SearchGroup:
    kind: SearchKind
    total: int
    best_score: float
    hits: list[SearchHit] = field(default_factory=list)


def _highlight(text: str | None, needle: str) -> Markup | None:
    """Escape `text`, wrapping the first case-insensitive occurrence of `needle` in <mark>."""
    if text is None:
        return None
    lowered = text.lower()
    # lower() can change the length of some characters, which would misalign the slices
    if len(lowered) != len(text) or (start := lowered.find(needle)) < 0:
        return escape(text)
    end = start + len(needle)
    return Markup("{}<mark>{}</mark>{}").format(text[:start], text[start:end], text[end:])


@router.get("")
def global_search(
    q: str = Query("", max_length=256),
    kind: str = Query("all"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    if kind != "all" and kind not in SEARCH_KINDS:
        raise exc.BadRequestException()

    if (query := Q.search.SearchQuery.parse(q)) is None:
        return responses.html_response()

    kinds = list(SEARCH_KINDS) if kind == "all" else [kind]
    session.execute(Q.search.threshold_statement())
    rows = session.execute(Q.search.search(
        query, kinds, limit_per_kind=PER_KIND_LIMIT if kind == "all" else SINGLE_KIND_LIMIT,
    )).all()

    groups: dict[str, SearchGroup] = {}
    # UNION ALL does not guarantee that each branch keeps its ORDER BY
    for row in sorted(rows, key=lambda r: (-r.score, -r.id)):
        search_kind = SEARCH_KINDS[row.kind]
        if (group := groups.get(row.kind)) is None:
            group = groups[row.kind] = SearchGroup(kind=search_kind, total=row.total, best_score=row.score)
        group.hits.append(SearchHit(
            url=str(responses.url_for(search_kind.endpoint, **{search_kind.id_param: row.id})),
            code=_highlight(row.code, query.text),
            label=_highlight(row.label, query.text) or escape(""),
            detail=row.detail,
        ))

    # most relevant kind first, so "BSR_0012" puts requests on top; ties keep the registry order
    order = list(SEARCH_KINDS)
    ranked = sorted(groups.values(), key=lambda g: (-g.best_score, order.index(g.kind.key)))

    return responses.html_response(
        template="components/global-search-results.html",
        groups=ranked, q=q.strip(), kind=kind,
    )
