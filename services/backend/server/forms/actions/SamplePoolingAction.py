import json
import pandas as pd

from fastapi import Depends, Response

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn, DBObjectColumn, InvalidCellValue, DuplicateCellValue
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


def _pooling_table(session: SyncSession, lab_prep_id: int) -> pd.DataFrame:
    """One row per sample link of the lab prep's multiplexed libraries, rejected samples included."""
    sample_table = T.lab_prep_pooling_table(
        session.get_pandas(Q.pd.lab_prep_pooling_table(lab_prep_id, include_rejected=True), limit=None),
        expand_mux_=False,
    )
    return sample_table[sample_table["mux_type"].notna()]


def _sample_label(name: str, sample_id: int, status: int | None) -> str:
    """Spreadsheet label of a sample, rejected samples are marked so they stand out."""
    if pd.notna(status) and int(status) == C.SampleStatus.REJECTED.id:
        return f"{name} {C.SampleStatus.REJECTED.icon} [{sample_id}]"
    return f"{name} [{sample_id}]"


class SamplePoolingAction(HTMXForm):
    template_path = "actions/sample-pooling.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        label="Sample Pooling",
        columns=[
            # Categories are the lab prep's samples, set in Init
            DBObjectColumn(("sample_id", "sample_name"), "Sample", 300, categories={}, required=True),
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
            session.get_one(Q.lab_prep.select(id=lab_prep_id))

            form = cls(lab_prep_id=lab_prep_id)

            sample_table = _pooling_table(session, lab_prep_id)
            samples = sample_table[["sample_id", "sample_name", "sample_status"]].drop_duplicates("sample_id")
            form.spreadsheet.columns["Sample"].set_categories({
                int(sample.sample_id): _sample_label(sample.sample_name, sample.sample_id, sample.sample_status)
                for sample in samples.sort_values("sample_name").itertuples()
            })
            mux_table = sample_table[["sample_id", "sample_name", "sample_pool"]].drop_duplicates(["sample_id", "sample_pool"])

            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                df=mux_table,
                post_url=responses.url_for("SamplePoolingAction.Submit", lab_prep_id=lab_prep_id),
            )

            return form
        return dependency

    @htmx_route("GET", "/sample-pooling/{lab_prep_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SamplePoolingAction" = Depends(SamplePoolingAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/sample-pooling/{lab_prep_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SamplePoolingAction" = Depends(SamplePoolingAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            lab_prep = session.get_one(Q.lab_prep.select(id=form.lab_prep_id))
            if lab_prep is None:
                raise exc.NotFoundException()

            df = form.spreadsheet.data
            assert df is not None

            sample_table = _pooling_table(session, form.lab_prep_id)
            pooled_ids = set(sample_table["sample_id"])

            # Each row is one (sample, pool) pair: a sample in several rows is pooled into several libraries
            seen: set[tuple[int, str]] = set()
            for idx, row in df.iterrows():
                sample_id, pool = int(row["sample_id"]), str(row["sample_pool"]).strip()
                df.at[idx, "sample_pool"] = pool
                if pool.lower() == "x":
                    form.spreadsheet.add_error(idx, "sample_pool", InvalidCellValue("To fail a sample, use the 'Reject Samples' step instead."))
                if (sample_id, pool) in seen:
                    form.spreadsheet.add_error(idx, ["Sample", "sample_pool"], DuplicateCellValue("Sample is listed in this pool more than once."))
                seen.add((sample_id, pool))

            if missing := pooled_ids - set(df["sample_id"]):
                names = sample_table.loc[sample_table["sample_id"].isin(missing), "sample_name"].drop_duplicates()
                form.spreadsheet.add_general_error(f"Every sample needs a pool, missing: {', '.join(sorted(names))}.")

            form.assert_valid()

            # Target layout: (pool, library type id) → sample → (barcode, library its link is copied from).
            # The barcode is taken from the sample's link in that pool, or, for a pool the sample is new to,
            # from its other links of that library type, which must agree.
            targets: dict[tuple[str, int], dict[int, tuple[dict | None, int]]] = {}
            for (sample_id, library_type), links in sample_table.groupby(["sample_id", "library_type"]):
                for pool in df.loc[df["sample_id"] == sample_id, "sample_pool"]:
                    if (in_pool := links[links["sample_pool"] == pool]).empty:
                        if links["mux"].map(lambda mux: json.dumps(mux, sort_keys=True, default=str)).nunique() > 1:
                            idx = df.index[(df["sample_id"] == sample_id) & (df["sample_pool"] == pool)][0]
                            form.spreadsheet.add_error(idx, "Sample", InvalidCellValue(
                                "Sample has different barcodes in its current pools, it cannot be added to a new pool."
                            ))
                            continue
                        in_pool = links
                    template = in_pool.iloc[0]
                    targets.setdefault((pool, int(library_type)), {})[int(sample_id)] = (template["mux"], int(template["library_id"]))

            form.assert_valid()

            # Re-use the existing libraries: first the one already in the pool, then a library of the same type
            # that loses its pool, sharing the most samples. Only the remaining pools get a new library.
            old_libraries = sample_table.groupby("library_id").agg(
                pool=("sample_pool", "first"), library_type=("library_type", "first"), sample_ids=("sample_id", set),
            )
            unused = set(old_libraries.index)
            assigned: dict[tuple[str, int], int] = {}
            for key in sorted(targets):
                for library_id in sorted(unused):
                    if (old_libraries.at[library_id, "pool"], old_libraries.at[library_id, "library_type"]) == key:
                        assigned[key] = library_id
                        unused.discard(library_id)
                        break

            candidates = sorted(
                (
                    (len(old_libraries.at[library_id, "sample_ids"] & samples.keys()), key, library_id)
                    for key, samples in targets.items() if key not in assigned
                    for library_id in unused if old_libraries.at[library_id, "library_type"] == key[1]
                ),
                key=lambda c: (-c[0], c[1], c[2]),
            )
            for _, key, library_id in candidates:
                if key not in assigned and library_id in unused:
                    assigned[key] = library_id
                    unused.discard(library_id)

            for key in sorted(targets):
                pool, library_type = key[0], C.LibraryType.get(key[1])
                samples = targets[key]
                if (library_id := assigned.get(key)) is not None:
                    library = session.get_one(Q.library.select(id=int(library_id)))
                    library.name = f"{pool}_{library_type.identifier}"
                    library.sample_name = pool
                else:
                    old_library = session.get_one(Q.library.select(id=min(template_id for _, template_id in samples.values())))
                    library = session.save(Q.library.create(
                        name=f"{pool}_{library_type.identifier}",
                        sample_name=pool,
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
                    library.features = old_library.features
                session.save(library, flush=True)

                current = {link.sample_id: link for link in library.sample_links}
                for sample_id, link in current.items():
                    if sample_id not in samples:
                        session.delete(link)
                for sample_id, (mux, _) in samples.items():
                    if (link := current.get(sample_id)) is None:
                        actions.link_sample_library(session=session, sample_id=sample_id, library_id=library.id, mux=mux, flush=False)
                    elif link.mux != mux:
                        link.mux = mux

            # Libraries without a pool are emptied and deleted below, once their samples are linked elsewhere
            for library_id in unused:
                library = session.get_one(Q.library.select(id=int(library_id)))
                for link in library.sample_links:
                    session.delete(link)

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