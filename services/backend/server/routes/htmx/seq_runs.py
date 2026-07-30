from fastapi import APIRouter

from ... import forms

router = APIRouter(prefix="/seq-runs", tags=["seq-runs"])

router.include_router(forms.models.SeqRunForm.Router())