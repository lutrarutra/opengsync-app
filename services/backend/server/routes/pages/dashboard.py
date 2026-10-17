from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
