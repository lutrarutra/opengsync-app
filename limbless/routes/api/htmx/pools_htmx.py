from typing import Optional, TYPE_CHECKING
from io import StringIO

import pandas as pd
from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, tools, PAGE_LIMIT
from ....core import DBSession, exceptions
from ....core.DBHandler import DBHandler
from ....categories import UserRole, HttpResponse, LibraryType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

pools_htmx = Blueprint("pools_htmx", __name__, url_prefix="/api/pools/")