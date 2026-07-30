from typing import Literal

from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class PlateForm(HTMXForm):
    template_path = "forms/plate.html"

    name = inputs.string.StringInputField(
        "Plate Name",
        max_length=models.Plate.name.type.length,
        required=True,
    )
    num_cols = inputs.numeric.IntInputField(
        "Number of Columns",
        required=True,
        default=12,
        ge=1,
    )
    num_rows = inputs.numeric.IntInputField(
        "Number of Rows",
        required=True,
        default=8,
        ge=1,
    )
    orientation = inputs.selectable.SelectableInputField(
        "Orientation",
        [(0, "Default"), (1, "Flipped")],
        default=0,
    )

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        pool: models.Pool | None,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.pool = pool

        if form_type == "create":
            if pool is not None:
                self.post_url = responses.url_for("PlateForm.Create", pool_id=pool.id)
            else:
                self.post_url = responses.url_for("PlateForm.Create")
        else:
            raise ValueError("PlateForm only supports 'create' form_type.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            pool_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "PlateForm":
            pool = None
            if pool_id is not None:
                pool = session.get_one(Q.pool.select(id=pool_id))
            return PlateForm(form_type=form_type, pool=pool)

        return dependency

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            pool_id: int | None = None,
            form: "PlateForm" = Depends(PlateForm.Init(form_type="create")),
            _=Depends(dependencies.require_insider),
        ):
            if form.pool is not None:
                form.name.data = form.pool.name
            return form.make_response()
        return route

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            pool_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
            form: "PlateForm" = Depends(PlateForm.Validate(form_type="create")),
        ) -> Response:
            flipped = form.orientation.data == 1

            plate = session.save(Q.plate.create(
                name=form.name.data,
                num_cols=form.num_cols.data,
                num_rows=form.num_rows.data,
                owner=current_user,
            ), flush=True)

            if form.pool is not None:
                libraries = session.get_all(
                    Q.library.select(pool_id=form.pool.id),
                    order_by=models.Library.id.asc(),
                    limit=None,
                )
                for i, library in enumerate(libraries):
                    plate.sample_links.append(models.links.SamplePlateLink(
                        plate_id=plate.id, well_idx=i, library_id=library.id
                    ))

                return responses.htmx_response(
                    redirect=responses.url_for("pool_page", pool_id=form.pool.id),
                    flash=responses.flash(f"Plate {plate.name} created.", "success"),
                )

            raise exc.OpeNGSyncServerException("Creating plates without a pool is not yet supported.")
        return submit