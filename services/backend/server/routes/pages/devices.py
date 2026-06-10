from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/")
async def devices():
    return await responses.html_response("devices_page.html", title="Devices")


@router.get("/{sequencer_id}")
async def sequencer(sequencer_id: int):
    # NOTE: Sequencer lookup and form generation are handled client-side
    # via API calls. The page renders with the sequencer_id for the frontend.
    return await responses.html_response(
        "device_page.html",
        sequencer_id=sequencer_id,
        title=f"Device {sequencer_id}",
    )