from typing import TypeVar

from fastapi import Depends

from ....core import responses
from ...HTMXForm import FormFunc
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


T = TypeVar("T", bound="LibraryAnnotationWorkflowStep")


class LibraryAnnotationWorkflowStep(HTMXWorkflowStep):
    """Base workflow step with standard Library Annotation construction."""

    workflow: LibraryAnnotationWorkflow

    @property
    def post_url(self) -> responses.URL:
        return self.PostURL(
            prefix="LibraryAnnotationWorkflow",
            seq_request_id=self.workflow.seq_request_id,
        ).include_query_params(uuid=self.workflow.uuid)

    @classmethod
    def Init(cls: type[T]) -> FormFunc:
        """Create this step from the workflow state for an endpoint dependency."""
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(
                LibraryAnnotationWorkflow.Init(cls.__name__)
            ),
        ) -> T:
            return cls(workflow=workflow)

        return dependency

    @classmethod
    def PreviousStep(cls: type[T]) -> FormFunc:
        """Get the previous step from the workflow state for an endpoint dependency."""
        def dependency(
            form: T = Depends(super(LibraryAnnotationWorkflowStep, cls).Init()),
        ) -> T:
            return form

        return dependency

    @classmethod
    def Validate(cls: type[T], **kwargs) -> FormFunc:
        """Validate this step from the workflow state for an endpoint dependency."""
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(
                LibraryAnnotationWorkflow.Init(cls.__name__),
                **kwargs
            ),
            form: T = Depends(super(LibraryAnnotationWorkflowStep, cls).Validate()),
        ) -> T:
            return form

        return dependency
