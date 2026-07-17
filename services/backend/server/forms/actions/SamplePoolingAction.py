from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn, IntegerColumn
from ...utils.parsing import map_columns
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class SamplePoolingAction(HTMXForm):
    template_path = "actions/sample-pooling.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        label="Sample Pooling",
        columns=[
            IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
            TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
            TextColumn("sample_pool", "Pool", 300, required=True, read_only=False),
        ],
        required=True,
    )

    def __init__(
        self,
        lab_prep_id: int,
    ) -> None:
        super().__init__()
        self.lab_prep_id = lab_prep_id

    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            lab_prep_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SamplePoolingAction":
            if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                raise exc.ItemNotFoundException()

            form = cls(lab_prep_id=lab_prep_id)

            sample_table = session.pd.get_lab_prep_pooling_table(lab_prep_id)
            sample_table = sample_table[sample_table["mux_type"].notna()]
            mux_table = sample_table[["sample_id", "sample_name", "sample_pool"]].drop_duplicates()

            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                df=mux_table,
                post_url=responses.url_for("SamplePoolingAction.Submit", lab_prep_id=lab_prep_id),
            )

            return form
        return dependency

    @htmx_route("GET", "/{lab_prep_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SamplePoolingAction" = Depends(SamplePoolingAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/{lab_prep_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SamplePoolingAction" = Depends(SamplePoolingAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            lab_prep = session.get_one(Q.lab_prep.select(id=form.lab_prep_id))
            if lab_prep is None:
                raise exc.ItemNotFoundException()

            df = form.spreadsheet.data
            assert df is not None

            sample_table = session.pd.get_lab_prep_pooling_table(form.lab_prep_id)
            sample_table = sample_table[sample_table["mux_type"].notna()]

            sample_table["new_sample_pool"] = map_columns(sample_table, df, "sample_id", "sample_pool")

            old_libraries: dict[int, models.Library] = {}

            for library_id in sample_table["library_id"].unique():
                if (library := session.first(Q.library.select(id=int(library_id)))) is None:
                    logger.error(f"Library {library_id} not found.")
                    raise exc.ItemNotFoundException(f"Library {library_id} not found.")

                old_libraries[library.id] = library
                library.sample_links.clear()
                session.save(library)
                session.flush()
                session.refresh(library)

            libraries: dict[str, models.Library] = {}

            for (new_sample_pool, library_id), _df in sample_table.groupby(["new_sample_pool", "library_id"]):
                old_library = session.get_one(Q.library.select(id=int(library_id)))  # type: ignore
                library_name = f"{new_sample_pool}_{old_library.type.identifier}" if new_sample_pool != "x" else f"canceled_samples_{old_library.type.identifier}"
                if (new_library := libraries.get(library_name)) is None:
                    new_library = session.save(Q.library.create(
                        name=library_name,
                        sample_name=new_sample_pool,  # type: ignore
                        library_type=old_library.type,
                        status=old_library.status,
                        owner_id=old_library.owner_id,
                        seq_request_id=old_library.seq_request_id,
                        lab_prep_id=form.lab_prep_id,
                        genome_ref=old_library.genome_ref,
                        service_type=old_library.service_type,
                        mux_type=old_library.mux_type,
                        nuclei_isolation=old_library.nuclei_isolation,
                        index_type=old_library.index_type,
                        original_library_id=old_library.original_library_id if old_library.original_library_id is not None else None,
                        clone_number=old_library.clone_number,
                    ))
                    libraries[library_name] = new_library

                new_library.features = old_library.features
                if new_sample_pool == "x":
                    new_library.status = C.LibraryStatus.FAILED
                session.save(new_library)

                for _, row in _df.iterrows():
                    if (sample := session.first(Q.sample.select(id=int(row["sample_id"])))) is None:
                        logger.error(f"Sample {row['sample_id']} not found.")
                        raise Exception(f"Sample {row['sample_id']} not found.")

                    actions.link_sample_library(
                        session=session,
                        sample_id=sample.id,
                        library_id=new_library.id,
                        mux=row["mux"],
                    )

            session.flush()
            session.refresh(lab_prep)
            for library in lab_prep.libraries:
                session.refresh(library)
                if len(library.sample_links) == 0:
                    session.delete(library)

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep_id),
                flash=responses.flash("Sample pool annotation processed successfully.", "success"),
            )
        return route