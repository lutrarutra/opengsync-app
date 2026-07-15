from typing import Sequence

import pandas as pd
from fastapi import Depends, Query, Response
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...components import inputs
from ...core import barcode_utils, dependencies, exceptions as exc, responses
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class CheckBarcodeClashesAction(HTMXForm):
    template_path = "workflows/check_barcode_clashes/select-samples.html"
    library_ids = inputs.tables.LibrarySelectTableField("Libraries", browse_context="barcode-clashes", indexed=True)

    def __init__(self):
        super().__init__()

    @classmethod
    def get_library_data(cls, libraries: Sequence[models.Library]) -> pd.DataFrame:
        library_data = {
            "library_id": [],
            "library_name": [],
            "pool": [],
            "pool_id": [],
            "sequence_i7": [],
            "sequence_i5": [],
            "kit_i7_id": [],
            "kit_i5_id": [],
            "index_type_id": [],
        }
        for library in libraries:
            for index in library.indices:
                library_data["library_id"].append(library.id)
                library_data["library_name"].append(library.name)
                library_data["pool"].append(library.pool.name if library.pool else None)
                library_data["pool_id"].append(library.pool.id if library.pool else None)
                library_data["sequence_i7"].append(index.sequence_i7)
                library_data["sequence_i5"].append(index.sequence_i5)
                library_data["kit_i7_id"].append(index.index_kit_i7_id)
                library_data["kit_i5_id"].append(index.index_kit_i5_id)
                library_data["index_type_id"].append(index.type.id)
        return pd.DataFrame(library_data)

    @classmethod
    def render_clashes_table(cls, libraries_df: pd.DataFrame, groupby: str | None = None) -> responses.Response:
        if groupby is None:
            libraries_df = barcode_utils.check_indices(libraries_df)
        elif groupby == "pool":
            libraries_df = barcode_utils.check_indices(libraries_df, groupby="pool_id").sort_values(["pool_id", "library_id"])
        elif groupby == "lane":
            libraries_df = barcode_utils.check_indices(libraries_df, groupby="lane_id").sort_values(["lane", "library_id"])

        warn_user = libraries_df["error"].notna().any() or libraries_df["warning"].notna().any()
        return responses.htmx_response("workflows/check_barcode_clashes/clashes.html", libraries_df=libraries_df, groupby=groupby, warn_user=warn_user)

    @htmx_route("GET", "/select-samples", name="SelectSamples")
    def RenderSelectSamples(cls) -> RouteFunc:
        def route(
            form: CheckBarcodeClashesAction = Depends(CheckBarcodeClashesAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/select-samples", name="SelectSamples")
    def Submit(cls) -> RouteFunc:
        def route(
            form: CheckBarcodeClashesAction = Depends(CheckBarcodeClashesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            if not form.library_ids.data:
                raise exc.BadRequestException("No libraries selected.")

            libraries = session.get_all(
                Q.library.select(ids=form.library_ids.data, viewer_id=current_user.id),
                options=[orm.selectinload(models.Library.indices), orm.selectinload(models.Library.pool)],
                limit=None
            )
            libraries_df = cls.get_library_data(libraries)
            return cls.render_clashes_table(libraries_df=libraries_df, groupby=None)
        return route
    
    @htmx_route("GET", path="/")
    def Render(cls) -> RouteFunc:
        def route(
            seq_request_id: int | None = Query(None, description="ID of the sequencing request to check barcodes for."),
            pool_id: int | None = Query(None, description="ID of the pool to check barcodes for."),
            experiment_id: int | None = Query(None, description="ID of the experiment to check barcodes for."),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            groupby: str | None = None
            if seq_request_id is not None:
                if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
                    raise exc.NoPermissionsException("You do not have permission to view libraries for this seq request.")
                libraries = session.get_all(Q.library.select(seq_request_id=seq_request_id), limit=None, options=[orm.selectinload(models.Library.indices), orm.selectinload(models.Library.pool)])
                libraries_df = cls.get_library_data(libraries)
                groupby = "pool"
            elif pool_id is not None:
                if session.get_access_level(Q.pool.permissions(pool_id, current_user.id)) < C.AccessLevel.READ:
                    raise exc.NoPermissionsException("You do not have permission to view libraries for this pool.")
                libraries = session.get_all(Q.library.select(pool_id=pool_id), options=[orm.selectinload(models.Library.indices)])
                libraries_df = cls.get_library_data(libraries)
            elif experiment_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to view libraries for this experiment.")
                libraries_df = session.pd.get_experiment_barcodes(experiment_id=experiment_id)
                groupby = "lane"
            else:
                raise exc.BadRequestException("Must provide either seq_request_id, pool_id, or experiment_id to check barcodes for.")
            return cls.render_clashes_table(libraries_df=libraries_df, groupby=groupby)
        return route