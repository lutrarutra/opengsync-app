from typing import Literal

from fastapi import Depends, Request
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import AsyncSession, models, queries as Q, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm


class PoolForm(HTMXForm):
    template_path = "forms/pool.html"

    name = inputs.string.StringInputField("Pool Name", max_length=models.Pool.name.type.length, min_length=4)
    pool_type = inputs.selectable.SelectableInputField("Pool Type", options=C.PoolType.as_selectable())
    num_m_reads_requested = inputs.numeric.FloatInputField("Number of M Reads Requested", required=False)
    status = inputs.selectable.SelectableInputField("Status", options=C.PoolStatus.as_selectable())
    contact = inputs.searchable.SearchableInputField("Contact", route="search_users", required=False)
    contact_name = inputs.string.StringInputField("Contact Name", max_length=models.Contact.name.type.length)
    contact_email = inputs.string.StringInputField("Contact Email", max_length=models.Contact.email.type.length)
    contact_phone = inputs.string.StringInputField("Contact Phone", required=False, max_length=models.Contact.phone.type.length)

    def __init__(
        self,
        request: Request,
        form_type: Literal["create", "edit", "clone"],
        pool: models.Pool | None = None,
    ) -> None:
        super().__init__(request)
        self.form_type = form_type
        self.pool = pool

        if form_type in ("edit", "clone") and pool is None:
            raise exc.OpeNGSyncServerException(
                "Pool must be provided when form_type is 'edit' or 'clone'."
            )
        if form_type == "create" and pool is not None:
            raise exc.OpeNGSyncServerException(
                "Pool must be None when form_type is 'create'."
            )

    async def prepare(self) -> None:
        if self.form_type == "create":
            self.contact.data = self.request.state.current_user.id
            self._context["form_type"] = "create"
        elif self.form_type in ("edit", "clone") and self.pool is not None:
            self.name.data = self.pool.name
            self.pool_type.data = self.pool.type_id
            self.num_m_reads_requested.data = self.pool.num_m_reads_requested

            if self.form_type == "clone":
                self.status.data = C.PoolStatus.STORED.id
            else:
                self.status.data = self.pool.status_id

            if self.pool.contact is not None:
                self.contact_name.data = self.pool.contact.name
                self.contact_email.data = self.pool.contact.email or ""
                self.contact_phone.data = self.pool.contact.phone

            self._context["form_type"] = self.form_type
            self._context["pool"] = self.pool

    @staticmethod
    async def create(
        request: Request,
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        form = PoolForm(request, form_type="create")
        await form.validate()

        if not form.contact_name.data and form.contact.data is None:
            form.contact_name.errors.append("Select an existing contact or provide a name.")

        if not form.contact_email.data and form.contact.data is None:
            form.contact_email.errors.append("Select an existing contact or provide an email.")

        contact_id = form.contact.data
        contact_obj = None
        if contact_id is not None:
            contact_obj = await session.first(Q.user.select(id=contact_id))

        pool_type = C.PoolType.get(form.pool_type.data)

        pool = await session.save(Q.pool.create(
            name=form.name.data,
            status=C.PoolStatus.get(form.status.data),
            num_m_reads_requested=form.num_m_reads_requested.data,
            owner_id=request.state.current_user.id,
            pool_type=pool_type,
            contact_name=form.contact_name.data if contact_obj is None else contact_obj.name,
            contact_email=form.contact_email.data if contact_obj is None else contact_obj.email,
            contact_phone=form.contact_phone.data,
            clone_number=0,
        ), flush=True)

        return await responses.htmx_response(
            redirect=request.url_for("pool_page", pool_id=pool.id),
            flash=responses.flash("Pool Created!", "success"),
        )

    @staticmethod
    async def edit(
        pool_id: int,
        request: Request,
        session: AsyncSession = Depends(dependencies.db_session),
        access_level: C.AccessLevel = Depends(dependencies.pool_permissions),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException(
                "You do not have permission to edit this pool."
            )

        pool = await session.get_one(Q.pool.select(id=pool_id).options(
            orm.selectinload(models.Pool.contact),
        ))

        form = PoolForm(request, form_type="edit", pool=pool)
        await form.validate()

        pool.name = form.name.data
        pool.status_id = form.status.data
        pool.type_id = form.pool_type.data
        pool.num_m_reads_requested = form.num_m_reads_requested.data
        pool.contact.name = form.contact_name.data
        pool.contact.email = form.contact_email.data
        pool.contact.phone = form.contact_phone.data

        return await responses.htmx_response(
            redirect=request.url_for("pool_page", pool_id=pool.id),
            flash=responses.flash("Changes Saved!", "success"),
        )

    @staticmethod
    async def clone(
        pool_id: int,
        request: Request,
        session: AsyncSession = Depends(dependencies.db_session),
        current_user: models.User = Depends(dependencies.require_insider),
    ) -> Response:
        pool = await session.get_one(Q.pool.select(id=pool_id).options(
            orm.selectinload(models.Pool.contact),
            orm.selectinload(models.Pool.libraries),
            orm.selectinload(models.Pool.dilutions),
        ))

        form = PoolForm(request, form_type="clone", pool=pool)
        await form.validate()

        pool_type = C.PoolType.get(form.pool_type.data)
        if pool_type != pool.type:
            form.pool_type.errors.append(
                "Pool type cannot be changed. Please create a new pool instead."
            )

        cloned_pool = await session.save(Q.pool.create(
            name=form.name.data,
            status=C.PoolStatus.STORED,
            num_m_reads_requested=form.num_m_reads_requested.data,
            owner_id=request.state.current_user.id,
            pool_type=pool.type,
            contact_email=(
                pool.contact.email if pool.contact.email else "unknown"
            ),
            contact_name=pool.contact.name,
            contact_phone=pool.contact.phone,
            seq_request_id=pool.seq_request_id,
            original_pool_id=(
                pool.original_pool_id
                if pool.original_pool_id is not None
                else pool.id
            ),
            clone_number=0,
        ), flush=True)

        cloned_pool.ba_report_id = pool.ba_report_id
        cloned_pool.avg_fragment_size = pool.avg_fragment_size
        cloned_pool.qubit_concentration = pool.qubit_concentration

        for dilution in pool.dilutions:
            cloned_pool.dilutions.append(models.PoolDilution(
                pool_id=cloned_pool.id,
                operator_id=dilution.operator_id,
                identifier=dilution.identifier,
                qubit_concentration=dilution.qubit_concentration,
                volume_ul=dilution.volume_ul,
                timestamp_utc=dilution.timestamp_utc,
            ))

        await session.flush()

        for library in pool.libraries:
            cloned_lib = await session.save(Q.library.create(
                name=library.name,
                sample_name=library.sample_name,
                library_type=library.type,
                seq_request_id=library.seq_request_id,
                owner_id=library.owner_id,
                genome_ref=library.genome_ref,
                service_type=library.service_type,
                mux_type=library.mux_type,
                properties=library.properties,
                index_type=library.index_type,
                nuclei_isolation=library.nuclei_isolation,
                clone_number=library.clone_number + 1,
                original_library_id=(
                    library.original_library_id
                    if library.original_library_id is not None
                    else library.id
                ),
                status=C.LibraryStatus.POOLED,
            ), flush=True)
            cloned_lib.pool_id = cloned_pool.id

        return await responses.htmx_response(
            redirect=request.url_for("pool_page", pool_id=cloned_pool.id),
            flash=responses.flash("Pool Cloned!", "success"),
        )
