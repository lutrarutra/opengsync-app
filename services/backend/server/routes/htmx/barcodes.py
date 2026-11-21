import os
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import (
    models,
    SyncSession,
    queries as Q,
    categories as C,
    actions,
    utils,
)

from ...core import dependencies, responses, exceptions as exc, config
from ... import forms

router = APIRouter(prefix="/barcodes", tags=["barcodes"])
