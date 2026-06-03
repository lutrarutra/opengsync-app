from fastapi import APIRouter, Depends, Query, Request, Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ...core import dependencies, responses, secrets
from ... import forms

router = APIRouter(prefix="/lab_preps", tags=["lab_preps"])

@router.get("/create")
def get_lab_prep_form(
    form: forms.models.LabPrepForm = Depends(forms.models.LabPrepForm),
):
    return form.make_response()

