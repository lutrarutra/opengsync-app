"""Statuses set by hand in edit forms (insiders). Any status to any status; users may add a comment."""
from ._common import *  # noqa: F401,F403
from ._common import collect

EDIT_POOL = operation(
    "manual.edit_pool", "Edit pool", K.MANUAL, E.POOL, effect(E.POOL, ANY, ANY),
    where=[B + "forms/models/PoolForm.py"],
)
EDIT_PROJECT = operation(
    "manual.edit_project", "Edit project", K.MANUAL, E.PROJECT, effect(E.PROJECT, ANY, ANY),
    where=[B + "forms/models/ProjectForm.py"],
)
EDIT_LIBRARY = operation(
    "manual.edit_library", "Edit library", K.MANUAL, E.LIBRARY, effect(E.LIBRARY, ANY, ANY),
    where=[B + "forms/models/LibraryForm.py"],
)
EDIT_SAMPLE = operation(
    "manual.edit_sample", "Edit sample", K.MANUAL, E.SAMPLE, effect(E.SAMPLE, ANY, ANY),
    where=[B + "forms/models/SampleForm.py"],
)
EDIT_EXPERIMENT = operation(
    "manual.edit_experiment", "Edit experiment", K.MANUAL, E.EXPERIMENT, effect(E.EXPERIMENT, ANY, ANY),
    where=[B + "forms/models/ExperimentForm.py"],
)
EDIT_SEQ_RUN = operation(
    "manual.edit_seq_run", "Edit seq run", K.MANUAL, E.SEQ_RUN, effect(E.SEQ_RUN, ANY, ANY),
    where=[B + "forms/models/SeqRunForm.py"],
)
CREATE_SEQ_RUN = operation(
    "manual.create_seq_run", "Create seq run", K.MANUAL, E.SEQ_RUN,
    effect(E.SEQ_RUN, NEW, ANY, when="chosen status"),
    effect(E.EXPERIMENT, ANY, [EX.SEQUENCING, EX.SEQUENCED, EX.FAILED, EX.ARCHIVED], via="experiment",
           when="same-named experiment, mapped from the run status (RUNNING, FINISHED, FAILED, ARCHIVED)"),
    where=[B + "forms/models/SeqRunForm.py"],
)
SET_ROUTE = operation(
    "manual.set_route", "Set request route", K.MANUAL, E.SEQ_REQUEST,
    doc="Overrides the inferred route of a request; changes no status.",
)

ALL = collect(globals())
