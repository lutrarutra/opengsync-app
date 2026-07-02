from abc import ABC, abstractmethod
from fastapi import Request, Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import responses, exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import HTMXForm
from .HTMXWorkflow import HTMXWorkflow

class HTMXWorkflowStep(HTMXForm, ABC):
    """
    Abstract base class for HTMX workflow steps.
    Each step in a workflow should inherit from this class and implement the required methods.
    """

    def is_applicable(self, workflow: "HTMXWorkflow") -> bool:
        return True
    