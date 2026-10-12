"""Kinds shown by the navbar search: how each one is labelled, drawn and linked.

Matching lives in opengsync_db.queries.search; adding a kind means a branch there and an entry here.
The CSS class `gs-kind-<key>` (static/style/global-search.css) gives each kind its colour.
"""
from dataclasses import dataclass

from opengsync_db import queries as Q


@dataclass(frozen=True)
class SearchKind:
    key: str
    label: str
    plural: str
    icon: str
    endpoint: str
    id_param: str


SEARCH_KINDS: dict[str, SearchKind] = {kind.key: kind for kind in (
    SearchKind("seq_request", "Request", "Requests", "bi-inbox", "seq_request_page", "seq_request_id"),
    SearchKind("project", "Project", "Projects", "bi-folder", "project_page", "project_id"),
    SearchKind("experiment", "Experiment", "Experiments", "bi-hdd-rack", "experiment_page", "experiment_id"),
    SearchKind("lab_prep", "Prep", "Preps", "bi-eyedropper", "lab_prep_page", "lab_prep_id"),
    SearchKind("pool", "Pool", "Pools", "bi-droplet", "pool_page", "pool_id"),
    SearchKind("sample", "Sample", "Samples", "bi-prescription2", "sample_page", "sample_id"),
    SearchKind("library", "Library", "Libraries", "bi-flask", "library_page", "library_id"),
    SearchKind("user", "User", "Users", "bi-person", "user_page", "user_id"),
    SearchKind("group", "Group", "Groups", "bi-people", "group_page", "group_id"),
    SearchKind("index_kit", "Index kit", "Index kits", "bi-upc", "index_kit_page", "index_kit_id"),
    SearchKind("library_kit", "Library kit", "Library kits", "bi-box-seam", "kit_page", "kit_id"),
    SearchKind("feature_kit", "Feature kit", "Feature kits", "bi-tags", "feature_kit_page", "feature_kit_id"),
    SearchKind("protocol", "Protocol", "Protocols", "bi-journal-text", "protocol_page", "protocol_id"),
)}

assert tuple(SEARCH_KINDS) == Q.search.KINDS, "SEARCH_KINDS must list the kinds of queries.search in order"
