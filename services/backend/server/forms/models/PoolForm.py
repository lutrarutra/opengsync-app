from typing import Literal

from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


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
        form_type: Literal["create", "edit", "clone"],
        pool: models.Pool | None = None,
    ) -> None:
        super().__init__()
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

    @classmethod
    def Init(cls, form_type: Literal["create", "edit", "clone"]) -> FormFunc:
        def dependency(
            pool_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "PoolForm":
            pool = None
            if pool_id is not None:
                pool = session.get_one(Q.pool.select(id=pool_id).options(
                    orm.selectinload(models.Pool.contact),
                ))
            return PoolForm(form_type=form_type, pool=pool)
        return dependency

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            form: "PoolForm" = Depends(PoolForm.Init(form_type="create")),
        ):
            form.contact.data = current_user.id
            return form.make_response()
        return route

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            form: "PoolForm" = Depends(PoolForm.Validate(form_type="create")),
        ) -> Response:
            if not form.contact_name.data and form.contact.data is None:
                form.contact_name.errors.append("Select an existing contact or provide a name.")

            if not form.contact_email.data and form.contact.data is None:
                form.contact_email.errors.append("Select an existing contact or provide an email.")

            if form.errors:
                raise exc.FormValidationException(form)

            contact_id = form.contact.data
            contact_obj = None
            if contact_id is not None:
                contact_obj = session.first(Q.user.select(id=contact_id))

            pool_type = C.PoolType.get(form.pool_type.data)

            pool = session.save(Q.pool.create(
                name=form.name.data,
                status=C.PoolStatus.get(form.status.data),
                num_m_reads_requested=form.num_m_reads_requested.data,
                owner_id=current_user.id,
                pool_type=pool_type,
                contact_name=form.contact_name.data if contact_obj is None else contact_obj.name,
                contact_email=form.contact_email.data if contact_obj is None else contact_obj.email,
                contact_phone=form.contact_phone.data,
                clone_number=0,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("pool_page", pool_id=pool.id),
                flash=responses.flash("Pool Created!", "success"),
            )
        return submit

    @htmx_route("GET", "/{pool_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            access_level: C.AccessLevel = Depends(dependencies.pool_permissions),
            form: "PoolForm" = Depends(PoolForm.Init(form_type="edit")),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this pool.")

            if form.pool is None:
                raise exc.OpeNGSyncServerException("Pool must be provided for edit form.")

            form.name.data = form.pool.name
            form.pool_type.data = form.pool.type_id
            form.num_m_reads_requested.data = form.pool.num_m_reads_requested
            form.status.data = form.pool.status_id

            if form.pool.contact is not None:
                form.contact_name.data = form.pool.contact.name
                form.contact_email.data = form.pool.contact.email or ""
                form.contact_phone.data = form.pool.contact.phone

            return form.make_response()
        return route

    @htmx_route("POST", "/{pool_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            access_level: C.AccessLevel = Depends(dependencies.pool_permissions),
            session: SyncSession = Depends(dependencies.db_session),
            form: "PoolForm" = Depends(PoolForm.Validate(form_type="edit")),
        ) -> Response:
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this pool.")

            if form.pool is None:
                raise exc.OpeNGSyncServerException("Pool must be provided for edit form.")

            form.pool.name = form.name.data
            form.pool.status_id = form.status.data
            form.pool.type_id = form.pool_type.data
            form.pool.num_m_reads_requested = form.num_m_reads_requested.data
            form.pool.contact.name = form.contact_name.data
            form.pool.contact.email = form.contact_email.data
            form.pool.contact.phone = form.contact_phone.data

            return responses.htmx_response(
                redirect=responses.url_for("pool_page", pool_id=form.pool.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return submit

    @htmx_route("GET", "/{pool_id}/clone", name="Clone")
    def RenderClone(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_insider),
            form: "PoolForm" = Depends(PoolForm.Init(form_type="clone")),
        ):
            if form.pool is None:
                raise exc.OpeNGSyncServerException("Pool must be provided for clone form.")

            form.name.data = form.pool.name
            form.pool_type.data = form.pool.type_id
            form.num_m_reads_requested.data = form.pool.num_m_reads_requested
            form.status.data = C.PoolStatus.STORED.id

            if form.pool.contact is not None:
                form.contact_name.data = form.pool.contact.name
                form.contact_email.data = form.pool.contact.email or ""
                form.contact_phone.data = form.pool.contact.phone

            return form.make_response()
        return route

    @htmx_route("POST", "/{pool_id}/clone", name="Clone")
    def Clone(cls) -> RouteFunc:
        def submit(
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            form: "PoolForm" = Depends(PoolForm.Validate(form_type="clone")),
        ) -> Response:
            if form.pool is None:
                raise exc.OpeNGSyncServerException("Pool must be provided for clone form.")

            pool = session.get_one(Q.pool.select(id=form.pool.id).options(
                orm.selectinload(models.Pool.contact),
                orm.selectinload(models.Pool.libraries),
                orm.selectinload(models.Pool.dilutions),
            ))

            pool_type = C.PoolType.get(form.pool_type.data)
            if pool_type != pool.type:
                form.pool_type.errors.append(
                    "Pool type cannot be changed. Please create a new pool instead."
                )
                raise exc.FormValidationException(form)

            cloned_pool = session.save(Q.pool.create(
                name=form.name.data,
                status=C.PoolStatus.STORED,
                num_m_reads_requested=form.num_m_reads_requested.data,
                owner_id=current_user.id,
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

            session.flush()

            for library in pool.libraries:
                cloned_lib = session.save(Q.library.create(
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

            return responses.htmx_response(
                redirect=responses.url_for("pool_page", pool_id=cloned_pool.id),
                flash=responses.flash("Pool Cloned!", "success"),
            )
        return submit
