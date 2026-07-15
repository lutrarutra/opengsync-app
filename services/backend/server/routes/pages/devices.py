from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/")
def sequencers_page():
    return responses.html_response("devices_page.html", title="Devices")


@router.get("/{sequencer_id}")
def sequencer_page(sequencer_id: int):
    return responses.html_response(
        "device_page.html",
        sequencer_id=sequencer_id,
        title=f"Device {sequencer_id}",
    )