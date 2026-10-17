"""Manually checked checklist steps: the state stored on the owner plus one `ChecklistLog` row per change."""
from opengsync_db import models, SyncSession, categories as C

# owner model -> (attribute with the {step: bool} state, ChecklistLog foreign key, checklist type)
_OWNERS: dict[type, tuple[str, str, C.ChecklistType]] = {
    models.SeqRequest: ("review_checklist", "seq_request_id", C.ChecklistType.SEQ_REQUEST_REVIEW),
    models.Experiment: ("manual_checklist", "experiment_id", C.ChecklistType.EXPERIMENT),
}


def log_step(session: SyncSession, owner: models.SeqRequest | models.Experiment, step: str, checked: bool, actor_id: int) -> None:
    """Logs a manual check or uncheck without touching the stored state (for steps derived from data)."""
    _, foreign_key, checklist_type = _OWNERS[type(owner)]
    session.add(models.ChecklistLog(
        checklist_type=checklist_type, step=step, checked=checked, actor_id=actor_id, **{foreign_key: owner.id},
    ))


def set_step(session: SyncSession, owner: models.SeqRequest | models.Experiment, step: str, checked: bool, actor_id: int) -> bool:
    """Checks or unchecks `step` and logs it. Returns False, and logs nothing, if the step already had that state."""
    attr, _, _ = _OWNERS[type(owner)]
    if bool((getattr(owner, attr) or {}).get(step)) == checked:
        return False
    if getattr(owner, attr) is None:
        setattr(owner, attr, {})
    getattr(owner, attr)[step] = checked
    log_step(session, owner, step, checked, actor_id)
    session.save(owner)
    return True


def history(owner: models.SeqRequest | models.Experiment) -> dict[str, list[models.ChecklistLog]]:
    """The owner's log grouped by step, newest first (`checklist_logs` is ordered by time)."""
    _, _, checklist_type = _OWNERS[type(owner)]
    steps: dict[str, list[models.ChecklistLog]] = {}
    for log in owner.checklist_logs:
        if log.checklist_type == checklist_type:
            steps.setdefault(log.step, []).append(log)
    return steps
