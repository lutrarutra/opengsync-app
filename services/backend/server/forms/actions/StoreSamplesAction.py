from datetime import datetime

from fastapi import Depends, Response, Query
from loguru import logger

from opengsync_db import categories as C, SyncSession, queries as Q

from ...core import dependencies, exceptions, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm


class StoreSamplesAction(HTMXForm):
    template_path = "actions/store-samples.html"
    selected_sample_ids = inputs.tables.SampleSelectTableField(
        "Samples",
        "store-samples",
        status_in=[C.SampleStatus.WAITING_DELIVERY],
        select_all=True,
        required=False
    )
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "store-samples",
        status_in=[C.LibraryStatus.ACCEPTED],
        select_all=True,
        required=False
    )
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "store-samples",
        status_in=[C.PoolStatus.ACCEPTED],
        select_all=True,
        required=False
    )

    @htmx_route("GET")
    def Begin(cls) -> RouteFunc:
        def route(
            seq_request_id: int | None = Query(None),
            form: "StoreSamplesAction" = Depends(StoreSamplesAction.Init()),
        ):
            if seq_request_id is not None:
                form.selected_sample_ids.query_params["seq_request_id"] = seq_request_id
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            seq_request_id: int | None = Query(None),
            form: "StoreSamplesAction" = Depends(StoreSamplesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            context = {}
            if seq_request_id is not None:
                try:
                    seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
                    context["seq_request"] = seq_request
                except ValueError:
                    raise exceptions.BadRequestException()

            check_request_ids: set[int] = set()
            for sample in form.selected_sample_ids.get_selected_samples(session=session):
                sample.status = C.SampleStatus.STORED
                sample.timestamp_stored_utc = datetime.now()
                for library_link in sample.library_links:
                    if library_link.library.seq_request.status == C.SeqRequestStatus.ACCEPTED:
                        check_request_ids.add(library_link.library.seq_request.id)
                session.save(sample)

            for library in form.selected_library_ids.get_selected_libraries(session=session):
                if library.seq_request_id not in check_request_ids:
                    check_request_ids.add(library.seq_request_id)
                
                if library.is_pooled:
                    library.status = C.LibraryStatus.POOLED
                else:
                    library.status = C.LibraryStatus.STORED
                
                library.timestamp_stored_utc = datetime.now()
                session.save(library)

            for pool in form.selected_pool_ids.get_selected_pools(session=session):
                if pool.seq_request_id is not None:
                    check_request_ids.add(pool.seq_request_id)

                pool.status = C.PoolStatus.STORED
                pool.timestamp_stored_utc = datetime.now()
                session.save(pool)

            for _srid in check_request_ids:
                if (seq_request := session.first(Q.seq_request.select(id=_srid))) is None:
                    logger.error(f"SeqRequest {_srid} not found")
                    raise Exception(f"SeqRequest {_srid} not found")

                if seq_request.submission_type == C.SubmissionType.RAW_SAMPLES:
                    all_samples_stored = True
                    for sample in seq_request.samples:
                        all_samples_stored = sample.status >= C.SampleStatus.STORED and all_samples_stored
                        if not all_samples_stored:
                            break
                    if all_samples_stored:
                        seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
                        session.save(seq_request)

                elif seq_request.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    all_pools_stored = True
                    for pool in seq_request.pools:
                        all_pools_stored = pool.status >= C.PoolStatus.STORED and all_pools_stored
                        if not all_pools_stored:
                            logger.info(f"Pool {pool.id} status: {pool.status} not stored")
                            break
                    if all_pools_stored:
                        seq_request.status = C.SeqRequestStatus.PREPARED
                        session.save(seq_request)

                elif seq_request.submission_type == C.SubmissionType.UNPOOLED_LIBRARIES:
                    all_libraries_stored = True
                    for library in seq_request.libraries:
                        all_libraries_stored = library.status >= C.LibraryStatus.STORED and all_libraries_stored
                        if not all_libraries_stored:
                            break
                    if all_libraries_stored:
                        seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
                        session.save(seq_request)

            flash = responses.flash("Samples Stored!", "success")
            if seq_request_id is not None:
                return responses.htmx_response(redirect=responses.url_for("seq_request_page", seq_request_id=seq_request_id), flash=flash)
            
            return responses.htmx_response(redirect=responses.url_for("dashboard"), flash=flash)
        return route