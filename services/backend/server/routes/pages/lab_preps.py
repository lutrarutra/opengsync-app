from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/lab_preps", tags=["lab_preps"])


@router.get("/")
def lab_preps_page():
    return responses.html_response("lab_preps_page.html", title="Preps")


@router.get("/{lab_prep_id}")
def lab_prep_page(
    lab_prep_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    lab_prep = session.get_one(
        Q.lab_prep.select(id=lab_prep_id),
        options=[
            orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.sample_links),
            orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.indices),
            orm.selectinload(models.LabPrep.prep_file),
            orm.selectinload(models.LabPrep.media_files),
            orm.selectinload(models.LabPrep.plates),
            orm.selectinload(models.LabPrep.creator),
            orm.with_expression(models.LabPrep._num_pools, models.LabPrep.num_pools.expression),
            orm.with_expression(models.LabPrep._num_samples, models.LabPrep.num_samples.expression),
            orm.with_expression(models.LabPrep._num_plates, models.LabPrep.num_plates.expression),
            orm.with_expression(models.LabPrep._num_comments, models.LabPrep.num_comments.expression),
        ]
    )

    can_be_completed = len(lab_prep.libraries) > 0
    contains_mux_libraries = False
    for library in lab_prep.libraries:
        if library.status.id < C.LibraryStatus.POOLED.id or not library.is_indexed:
            can_be_completed = False
        
        if library.mux_type is not None:
            contains_mux_libraries = True
                
        if can_be_completed and contains_mux_libraries:
            break
        
    checklist = lab_prep.get_checklist()
    steps = [
        checklist["libraries_added"],
        checklist["library_fragment_sizes_measured"],
        checklist["libraries_indexed"],
        checklist["libraries_pooled"],
        checklist["protocols_selected"],
        checklist["lab_prep_completed"],
        checklist["oligo_mux_annotated"],
        checklist["flex_mux_annotated"],
        checklist["on_chip_mux_annotated"],
    ] 
    steps_completed = sum(1 for item in steps if item)

    return responses.html_response(
        "lab_prep_page.html",
        lab_prep=lab_prep,
        title=f"Prep {lab_prep.display_name}",
        can_be_completed=can_be_completed,
        contains_mux_libraries=contains_mux_libraries,
        checklist_steps_completed=steps_completed,
        checklist_total_steps=len(steps),
    )