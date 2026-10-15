"""Data release, delivery and project completion."""
from ._common import *  # noqa: F401,F403
from ._common import collect, FINISHED_LIBRARY

SHARE_DATA = operation(
    "project.share_data", "Share project data", K.ACTION, E.PROJECT,
    effect(E.PROJECT, below(PJ.DELIVERED), PJ.DELIVERED, when="'mark project delivered' is ticked, or all libraries ≥ SEQUENCED"),
    effect(E.DELIVERY_LINK, ANY, DL.DISPATCHED, via="libraries.seq_request.delivery_email_links", when="email is a recipient"),
    effect(E.LIBRARY, LB.SEQUENCED, LB.SHARED, via="libraries"),
    where=[B + "forms/actions/ShareProjectDataAction.py", DB + "core/actions.py:release_project_data"],
    doc="Same statuses as api.release_project (shared function).",
)

RELEASE = operation(
    "api.release_project", "Release project data (API)", K.API, E.PROJECT,
    effect(E.PROJECT, below(PJ.DELIVERED), PJ.DELIVERED, when="all libraries ≥ SEQUENCED, or forced with mark_project_delivered"),
    effect(E.DELIVERY_LINK, ANY, DL.DISPATCHED, via="libraries.seq_request.delivery_email_links", when="email is a recipient"),
    effect(E.LIBRARY, LB.SEQUENCED, LB.SHARED, via="libraries"),
    where=[B + "routes/api/shares.py:release_project_data", DB + "core/actions.py:release_project_data"],
)

COMPLETE = operation(
    "project.complete", "Complete project", K.ACTION, E.PROJECT,
    effect(E.PROJECT, ANY, PJ.DELIVERED),
    guard=rules.ChildrenAll(R.PROJECT_LIBRARIES, FINISHED_LIBRARY),
    where=[B + "routes/htmx/projects.py:complete_project"],
)

ARCHIVE = operation(
    "project.archive", "Archive project", K.ACTION, E.PROJECT,
    effect(E.PROJECT, ANY, PJ.ARCHIVED),
    where=[B + "routes/htmx/projects.py:archive_project"],
)

UNARCHIVE = operation(
    "project.unarchive", "Unarchive project", K.ACTION, E.PROJECT,
    effect(E.PROJECT, PJ.ARCHIVED, [PJ.DRAFT, PJ.DELIVERED, PJ.PROCESSING],
           when="DRAFT without libraries, DELIVERED if all libraries are finished, else PROCESSING"),
    guard=rules.StatusIn(frozenset([PJ.ARCHIVED])),
    where=[B + "routes/htmx/projects.py:unarchive_project"],
)

SPLIT = operation(
    "project.split", "Split project", K.WORKFLOW, E.PROJECT,
    effect(E.PROJECT, [NEW, *PJ], ANY, when="destination project gets the chosen status"),
    effect(E.SAMPLE, ANY, ANY, via="samples", when="a duplicate sample takes the further-along status"),
    where=[B + "forms/workflows/split_project/ConfirmSplitForm.py", DB + "core/actions.py:split_project"],
)

MERGE = operation(
    "project.merge", "Merge projects", K.ACTION, E.PROJECT,
    effect(E.SAMPLE, ANY, ANY, via="samples", when="a duplicate sample takes the further-along status"),
    where=[B + "forms/actions/MergeProjectsAction.py", DB + "core/actions.py:merge_projects"],
)

ALL = collect(globals())
