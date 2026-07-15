import pandas as pd

from fastapi import Depends, Response, Query
from loguru import logger

from opengsync_db import categories as C, SyncSession, queries as Q, models

from ...core import dependencies, exceptions, responses
from ...components import inputs
from ...components.tables import IntegerColumn, TextColumn, DuplicateCellValue
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class FlexMux:
    pass
