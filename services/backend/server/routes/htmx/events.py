from fastapi import APIRouter, Depends, Query


from opengsync_db import models

from .auth import dependencies

router = APIRouter(prefix="/events", tags=["events"])

@router.get("/render-month", dependencies=[Depends(dependencies.require_insider)])
async def events_month(
    year: int | None = Query(default=None, ge=2020, le=2100, description="Year of the events to render"),
    month: int | None = Query(default=None, ge=1, le=12, description="Month of the events to render"),
):
    pass


@router.get("/render-week", dependencies=[Depends(dependencies.require_insider)])
async def events_week(
    year: int | None = Query(default=None, ge=2020, le=2100, description="Year of the events to render"),
    week: int | None = Query(default=None, ge=1, le=53, description="Week number of the events to render"),
):
    pass