from typing import Any

from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies

router = APIRouter(tags=["api"])


@router.get("/validate-api_token")
def validate_api_token(current_user: models.User = Depends(dependencies.require_user)) -> dict[str, Any]:
    return {
        "result": "success",
        "owner_id": current_user.id,
        "owner_email": current_user.email,
    }
