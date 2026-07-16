import pandas as pd
from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q

from ....core import exceptions as exc, dependencies
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


class PoolMappingSubForm(SubHTMXForm):
    raw_label = inputs.string.StringInputField("Raw Label", required=True, read_only=True)
    new_pool_name = inputs.string.StringInputField("Pool Name", required=True, min_length=3, max_length=models.Pool.name.type.length)
    num_m_reads_requested = inputs.numeric.FloatInputField("Number of M Reads Requested", required=False)


class PoolMappingForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-pool_mapping.html"

    contact_name = inputs.string.StringInputField("Contact Name", required=True, max_length=models.Contact.name.type.length)
    contact_email = inputs.string.StringInputField("Contact Email", required=True, max_length=models.Contact.email.type.length)
    contact_phone = inputs.string.StringInputField("Contact Phone", required=True, max_length=models.Contact.phone.type.length)

    pool_forms = inputs.dynamic.SubFormList[PoolMappingSubForm](min_elements=0)

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        from loguru import logger
        logger.debug(self.library_table[["library_name", "pool"]])
        self.raw_pool_labels = self.library_table["pool"].unique().tolist()

    def prepare(self) -> None:
        """Prefill a new Pool Mapping step before its initial render."""
        if self.pool_forms.entries:
            return

        from ....core.context import ctx

        seq_request = ctx.session.get_one(
            Q.seq_request.select(id=self.workflow.seq_request_id).options(
                orm.joinedload(models.SeqRequest.contact_person)
            )
        )
        if seq_request.contact_person:
            if not self.contact_name.data:
                self.contact_name.data = seq_request.contact_person.name
            if not self.contact_email.data and seq_request.contact_person.email:
                self.contact_email.data = seq_request.contact_person.email
            if not self.contact_phone.data and seq_request.contact_person.phone:
                self.contact_phone.data = seq_request.contact_person.phone

        for pool in self.raw_pool_labels:
            entry = self.pool_forms.append_entry()
            entry.raw_label.data = str(pool)
            entry.new_pool_name.data = str(pool)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
        ) -> Response:
            form = PoolMappingForm(workflow=workflow)

            pool_table = workflow.tables["pool_table"]
            form.contact_name.data = workflow.metadata.get("pool_contact_name")
            form.contact_email.data = workflow.metadata.get("pool_contact_email")
            form.contact_phone.data = workflow.metadata.get("pool_contact_phone")

            form.pool_forms.entries.clear()
            for _, row in pool_table.iterrows():
                entry = form.pool_forms.append_entry()
                entry.raw_label.data = str(row["pool_label"])
                entry.new_pool_name.data = str(row["pool_name"])
                if pd.notna(row.get("num_m_reads_requested")):
                    entry.num_m_reads_requested.data = float(row["num_m_reads_requested"])

            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            form: PoolMappingForm = Depends(PoolMappingForm.Validate()),
        ) -> Response:
            workflow = form.workflow

            # Build pool table from validated entries
            pool_table_data = {
                "pool_name": [],
                "pool_label": [],
                "pool_id": [],
                "num_m_reads_requested": [],
            }

            def add_pool(name: str, label: str, pool_id: int | None, num_m_reads_requested: float | None) -> None:
                pool_table_data["pool_name"].append(name)
                pool_table_data["pool_label"].append(label)
                pool_table_data["pool_id"].append(pool_id)
                pool_table_data["num_m_reads_requested"].append(num_m_reads_requested)

            # Collect user's existing pool names for duplicate check
            existing_pool_names = {pool.name for pool in current_user.pools}
            submitted_names: set[str] = set()

            for entry in form.pool_forms:
                name = entry.new_pool_name.data
                if not name:
                    continue

                name = name.strip()
                if name in existing_pool_names:
                    entry.new_pool_name.errors.append("You already have a pool with this name.")
                    raise exc.FormValidationException(form)

                if name in submitted_names:
                    entry.new_pool_name.errors.append("Duplicate pool name within this submission.")
                    raise exc.FormValidationException(form)
                submitted_names.add(name)

                if (error := parsing.check_string(name)) is not None:
                    entry.new_pool_name.errors.append(error)
                    raise exc.FormValidationException(form)

                add_pool(
                    name=name,
                    label=entry.raw_label.data,  # type: ignore[arg-type]
                    pool_id=None,
                    num_m_reads_requested=entry.num_m_reads_requested.data,
                )

            pool_table = pd.DataFrame(pool_table_data)

            # Persist to workflow state
            workflow.metadata["pool_contact_name"] = form.contact_name.data
            workflow.metadata["pool_contact_email"] = form.contact_email.data
            workflow.metadata["pool_contact_phone"] = form.contact_phone.data
            workflow.tables["pool_table"] = pool_table
            from loguru import logger
            logger.debug(pool_table)
            return workflow.get_next_step(form).make_response()
        return route

