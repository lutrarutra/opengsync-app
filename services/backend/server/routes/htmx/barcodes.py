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
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/barcodes", tags=["barcodes"])


class BarcodeClashTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="Name", label="name", col_size=3),
    ]