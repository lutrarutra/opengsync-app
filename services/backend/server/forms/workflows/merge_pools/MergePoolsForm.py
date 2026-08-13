from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C, actions

from ....core import dependencies, exceptions as exc, responses
from ....core.context import ctx
from ....utils import barcodes
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .MergePoolsWorkflow import MergePoolsWorkflowStep, MergePoolsWorkflow


class PoolSubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", hidden=True)
    num_m_reads_requested = inputs.numeric.FloatInputField("Number of M Reads Requested", unit="m Reads")
    pipet = inputs.numeric.FloatInputField("Pipet Volume", unit="μL", default=20)


class MergePoolsForm(MergePoolsWorkflowStep):
    template_path = "workflows/merge_pools/merge-pools.html"

    name = inputs.string.StringInputField("Pool Name", max_length=models.Pool.name.type.length, min_length=4)
    pool_type = inputs.selectable.SelectableInputField("Pool Type", options=C.PoolType.as_selectable())
    num_m_reads_requested = inputs.numeric.FloatInputField("Number of M Reads Requested", required=False)
    status = inputs.selectable.SelectableInputField("Status", options=C.PoolStatus.as_selectable())
    contact = inputs.searchable.SearchableInputField("Contact", route="search_users", required=False)
    contact_name = inputs.string.StringInputField("Contact Name", required=False, max_length=models.Contact.name.type.length)
    contact_email = inputs.string.StringInputField("Contact Email", required=False, max_length=models.Contact.email.type.length)
    contact_phone = inputs.string.StringInputField("Contact Phone", required=False, max_length=models.Contact.phone.type.length)
    total_volume_ul = inputs.numeric.FloatInputField("Total Volume", unit="μL")
    pool_forms = inputs.dynamic.SubFormList[PoolSubForm](min_elements=2)

    def __init__(self, workflow: MergePoolsWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.pools: list[models.Pool] = []

    def prepare(self) -> None:
        session = ctx.session
        pool_table = self.workflow.tables["pool_table"]
        self.pools = [
            session.get_one(Q.pool.select(id=int(pool_id)).options(
                orm.selectinload(models.Pool.contact),
                orm.selectinload(models.Pool.owner),
                orm.selectinload(models.Pool.seq_request),
                orm.selectinload(models.Pool.lab_prep),
            ))
            for pool_id in pool_table["pool_id"].tolist()
        ]

        barcode_table = self.workflow.tables["barcode_table"]
        if barcode_table.empty:
            barcode_table = barcode_table.copy()
            barcode_table["error"] = None
            barcode_table["warning"] = None
        else:
            barcode_table = barcodes.check_indices(barcode_table)

        self._context["pools"] = self.pools
        self._context["barcode_table"] = barcode_table
        self._context["library_table"] = self.workflow.tables["library_table"]

        if self.pool_forms.entries:
            return

        current_user: models.User | None = getattr(ctx.request.state, "current_user", None)
        if current_user is not None:
            self.contact.data = current_user.id
            self.pool_type.data = C.PoolType.INTERNAL.id if current_user.is_insider else C.PoolType.EXTERNAL.id

        status = self.pools[0].status
        contact_id = self.pools[0].contact_id
        contact_name = self.pools[0].contact.name
        contact_email = self.pools[0].contact.email
        contact_phone = self.pools[0].contact.phone
        num_requested_reads: float | None = 0.0

        for pool in self.pools:
            entry = self.pool_forms.append_entry()
            entry.pool_id.data = pool.id
            entry.num_m_reads_requested.data = pool.num_m_reads_requested
            entry.pipet.data = 20

            if status is not None and pool.status != status:
                status = C.PoolStatus.DRAFT
            if contact_id is not None and pool.contact_id != contact_id:
                contact_id = None
            if contact_name is not None and pool.contact.name != contact_name:
                contact_name = None
            if contact_email is not None and pool.contact.email != contact_email:
                contact_email = None
            if contact_phone is not None and pool.contact.phone != contact_phone:
                contact_phone = None
            if pool.num_m_reads_requested is not None and num_requested_reads is not None:
                num_requested_reads += pool.num_m_reads_requested
            else:
                num_requested_reads = None

        self.num_m_reads_requested.data = num_requested_reads
        self.status.data = status.id if status is not None else C.PoolStatus.DRAFT.id
        if contact_id is not None:
            self.contact.data = contact_id
        self.contact_name.data = contact_name or ""
        self.contact_email.data = contact_email or ""
        self.contact_phone.data = contact_phone or ""

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "MergePoolsForm" = Depends(MergePoolsForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "MergePoolsForm" = Depends(MergePoolsForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            pool_table = form.workflow.tables["pool_table"]
            library_table = form.workflow.tables["library_table"]
            merged_names = set(pool_table["pool_name"].tolist())

            for pool in session.get_all(Q.pool.select(user_id=current_user.id), limit=None):
                if pool.name == form.name.data and pool.name not in merged_names:
                    form.name.errors.append("Owner of the pool already has a pool with the same name.")
                    break

            if form.contact.data is None:
                if not form.contact_name.data:
                    form.contact_name.errors.append("Contact is required")
                if not form.contact_email.data:
                    form.contact_email.errors.append("Contact is required")

            form.assert_valid()

            contact_obj = None
            if form.contact.data is not None:
                contact_obj = session.first(Q.user.select(id=form.contact.data))
                if contact_obj is None:
                    raise exc.ItemNotFoundException("Contact not found")

            pool = session.save(Q.pool.create(
                name=form.name.data,
                status=C.PoolStatus.get(form.status.data),
                num_m_reads_requested=form.num_m_reads_requested.data,
                owner_id=current_user.id,
                seq_request_id=form.workflow.seq_request_id,
                lab_prep_id=form.workflow.lab_prep_id,
                pool_type=C.PoolType.get(form.pool_type.data),
                contact_name=form.contact_name.data if contact_obj is None else contact_obj.name,
                contact_email=form.contact_email.data if contact_obj is None else (contact_obj.email or ""),
                contact_phone=form.contact_phone.data,
                clone_number=0,
            ), flush=True)

            source_pools: list[models.Pool] = []
            pool.merge_ratios = {}
            for entry in form.pool_forms.entries:
                pool.merge_ratios[str(entry.pool_id.data)] = {
                    "num_m_reads_requested": entry.num_m_reads_requested.data,
                    "pipet_volume_ul": entry.pipet.data,
                }
                source_pools.append(session.get_one(
                    Q.pool.select(id=entry.pool_id.data),
                    options=[orm.selectinload(models.Pool.libraries)],
                ))

            pool = actions.merge_pools(session, merged_pool=pool, pools=source_pools)
            pool = session.get_one(
                Q.pool.select(id=pool.id),
                options=[orm.selectinload(models.Pool.libraries)],
            )

            if len(pool.libraries) != len(library_table):
                raise exc.OpeNGSyncServerException("Mismatch in number of libraries after merging pools.")

            form.workflow.complete()
            return responses.htmx_response(
                redirect=responses.url_for("pool_page", pool_id=pool.id),
                flash=responses.flash("Pools Merged!", "success"),
            )
        return route
