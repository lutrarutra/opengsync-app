from fastapi import APIRouter, Depends

from ....core import dependencies
from ....forms import workflows as wf

router = APIRouter(prefix="/workflows", tags=["workflows"])

insider = [Depends(dependencies.require_insider)]
router.include_router(wf.library_annotation.LibraryAnnotationWorkflow.Router())

