import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, SyncSession, queries as Q, categories as C

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, exceptions as exc, responses, redis as rds
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn, IntegerColumn, DropdownColumn
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class RejectSamplesAction(HTMXForm):
    template_path = "actions/reject-samples.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        label="Reject Samples",
        columns=[
            IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
            TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
            TextColumn("sample_pool", "Pool", 300, required=False, read_only=True),
            TextColumn("status", "Status", 150, required=False, read_only=True),
            DropdownColumn("reject", "Reject", 100, choices=["x"], required=False),
        ],
        required=True,
    )

    def __init__(
        self,
        lab_prep_id: int,
    ) -> None:
        super().__init__()
        self.lab_prep_id = lab_prep_id

    @staticmethod
    def get_sample_table(session: SyncSession, lab_prep_id: int) -> pd.DataFrame:
        sample_table = T.lab_prep_pooling_table(
            session.get_pandas(Q.pd.lab_prep_pooling_table(lab_prep_id, include_rejected=True), limit=None),
            expand_mux_=False,
        )
        sample_table = sample_table[sample_table["mux_type"].notna()]
        return sample_table.drop_duplicates(subset=["sample_id"]).reset_index(drop=True)

    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            lab_prep_id: int,
            user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "RejectSamplesAction":
            if session.first(Q.lab_prep.select(id=lab_prep_id)) is None:
                raise exc.NotFoundException()

            form = cls(lab_prep_id=lab_prep_id)

            sample_table = RejectSamplesAction.get_sample_table(session, lab_prep_id)
            df = pd.DataFrame({
                "sample_id": sample_table["sample_id"],
                "sample_name": sample_table["sample_name"],
                "sample_pool": sample_table["sample_pool"],
                "status": sample_table["sample_status"].apply(lambda s: s.display_name if s is not None else None),
                "reject": sample_table["sample_status"].apply(lambda s: "x" if s == C.SampleStatus.REJECTED else None),
            })

            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                df=df,
                post_url=responses.url_for("RejectSamplesAction.Submit", lab_prep_id=lab_prep_id),
            )

            return form
        return dependency

    @htmx_route("GET", "/reject-samples/{lab_prep_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "RejectSamplesAction" = Depends(RejectSamplesAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/reject-samples/{lab_prep_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "RejectSamplesAction" = Depends(RejectSamplesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            r: rds.RedisClient = Depends(dependencies.redis),
        ) -> Response:
            if session.first(Q.lab_prep.select(id=form.lab_prep_id)) is None:
                raise exc.NotFoundException()

            df = form.spreadsheet.data
            assert df is not None

            rejected_ids = {
                int(row["sample_id"]) for _, row in df.iterrows()
                if pd.notna(row["reject"]) and str(row["reject"]).strip().lower() == "x"
            }

            # Only samples of this prep's multiplexed libraries can be (un-)rejected
            num_rejected = num_restored = 0
            for sample_id in RejectSamplesAction.get_sample_table(session, form.lab_prep_id)["sample_id"]:
                sample = session.get_one(Q.sample.select(id=int(sample_id)))
                if sample.id in rejected_ids and sample.status != C.SampleStatus.REJECTED:
                    sample.status = C.SampleStatus.REJECTED
                    num_rejected += 1
                elif sample.id not in rejected_ids and sample.status == C.SampleStatus.REJECTED:
                    sample.status = C.SampleStatus.STORED
                    num_restored += 1
                else:
                    continue

                session.save(sample)
                # Write access depends on the sample status
                for key in r.scan_iter(match=f"access:sample:{sample.id}:user:*"):
                    r.delete(key)

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep_id),
                flash=responses.flash(f"Rejected {num_rejected} and restored {num_restored} sample(s).", "success"),
            )
        return route
