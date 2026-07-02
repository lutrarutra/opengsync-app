from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])
