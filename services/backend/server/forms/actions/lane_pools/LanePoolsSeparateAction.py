import os
from uuid6 import uuid7

import pandas as pd
from fastapi import Depends
from sqlalchemy import orm
import sqlalchemy as sa
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses, config
from ....core.context import ctx
from ....components import inputs
from ....utils import parsing
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm

DEFAULT_TARGET_NM = 3.0
DEFAULT_TOTAL_VOLUME_TARGET = 50.0

class LanedGroupSchema(BaseModel):
    lane: int
    lane_id: int

class PoolRowSchema(BaseModel):
    pool_id: int
    num_m_reads: float | None
    qubit_concentration: float | None
    avg_fragment_size: int | None


class SampleSubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", required=True, read_only=True, hidden=True)
    lane = inputs.numeric.IntInputField("Lane", required=True, read_only=True, hidden=True)
    m_reads = inputs.numeric.FloatInputField("M Reads", required=True, ge=0.0, unit="M")
    dilution = inputs.string.StringInputField("Dilution", required=False, hidden=True)


class LaneSubForm(SubHTMXForm):
    lane = inputs.numeric.IntInputField("Lane", required=True, read_only=True, hidden=True)
    target_total_volume = inputs.numeric.FloatInputField(
        "Target Total Volume (µL)", required=True, default=DEFAULT_TOTAL_VOLUME_TARGET, ge=0.0, unit="μL"
    )
    target_concentration = inputs.numeric.FloatInputField(
        "Target Molarity (nM)", required=True, default=DEFAULT_TARGET_NM, ge=0.0, unit="nM"
    )


class LanePoolsSeparateAction(HTMXForm):
    template_path = "actions/lane-pools-separate.html"

    sample_sub_forms = inputs.dynamic.SubFormList[SampleSubForm](min_elements=1)
    lane_sub_forms = inputs.dynamic.SubFormList[LaneSubForm](min_elements=1)

    def __init__(self, experiment: models.Experiment) -> None:
        super().__init__()
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> "LanePoolsSeparateAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links).selectinload(models.links.LanePoolLink.lane)
            ))
            if experiment.workflow.combined_lanes:
                raise exc.BadRequestException("This experiment uses a combined lane workflow, not a separate lane workflow.")
            form = cls(experiment=experiment)
            # The table is also needed to re-render the form after a failed submit
            form._prepare(session, prefill=ctx.request.method == "GET")
            return form
        return dependency

    def _prepare(self, session: SyncSession, prefill: bool) -> None:
        df = session.get_pandas(
            Q.pd.experiment_laned_pools(self.experiment.id),
            limit=None,
        )
        df["dilutions"] = None
        for column in ("num_m_reads", "qubit_concentration", "molarity"):
            df[column] = pd.to_numeric(df[column], errors="coerce").astype(float)

        for group, _df in parsing.safe_groupby(df, LanedGroupSchema):
            if prefill:
                lane_sub = self.lane_sub_forms.append_entry()
                lane_sub.lane.data = group.lane

            for idx, row in parsing.safe_iter(_df, PoolRowSchema):
                if prefill:
                    sample_sub = self.sample_sub_forms.append_entry()
                    sample_sub.pool_id.data = row.pool_id
                    sample_sub.lane.data = group.lane
                    sample_sub.m_reads.data = row.num_m_reads
                    sample_sub.dilution.data = "Orig."

                pool = session.get_one(Q.pool.select(id=row.pool_id))
                df.at[idx, "dilutions"] = [("Orig.", pool.qubit_concentration, pool.molarity, "")]  # type: ignore

                for dilution in pool.dilutions:
                    if prefill:
                        sample_sub.dilution.data = dilution.identifier
                    df.at[idx, "dilutions"].append((dilution.identifier, dilution.qubit_concentration, dilution.molarity(pool), dilution.timestamp_str()))  # type: ignore
                    df.at[idx, "qubit_concentration"] = dilution.qubit_concentration
                    df.at[idx, "molarity"] = dilution.molarity(pool)

        df["share"] = float("nan")
        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "share"] = _df["num_m_reads"] / _df["num_m_reads"].sum()
        df["pipet"] = DEFAULT_TARGET_NM / df["molarity"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET
        self._context["df"] = df

    def get_context(self) -> dict:
        context = super().get_context()
        # Pair rows with their sub-forms by (lane, pool) (posted entries after a failed submit)
        lane_entries = {str(entry.lane.data): entry for entry in self.lane_sub_forms}
        sample_entries = {(str(entry.lane.data), str(entry.pool_id.data)): entry for entry in self.sample_sub_forms}
        context["lanes"] = [
            (
                lane,
                lane_entries.get(str(lane)),
                [(row, sample_entries.get((str(lane), str(row["pool_id"])))) for _, row in _df.iterrows()],
                _df["pipet"].sum(),
            )
            for lane, _df in context["df"].groupby("lane")
        ]
        return context

    @htmx_route("GET", "/{experiment_id}/lane-pools/separate")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LanePoolsSeparateAction" = Depends(LanePoolsSeparateAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/lane-pools/separate")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LanePoolsSeparateAction" = Depends(LanePoolsSeparateAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            for lane_sub_form in form.lane_sub_forms:
                lane = session.get_one(Q.lane.select(experiment_id=form.experiment.id, number=lane_sub_form.lane.data))
                lane.target_molarity = lane_sub_form.target_concentration.data
                lane.total_volume_ul = lane_sub_form.target_total_volume.data
                session.save(lane)

            data = {
                "lane": [],
                "pool": [],
                "lane_id": [],
                "pool_id": [],
                "num_m_reads": [],
                "qubit_concentration": [],
                "target_total_volume": [],
                "target_concentration": [],
                "avg_fragment_size": [],
                "molarity": [],
                "dilution": [],
            }

            for sample_sub_form in form.sample_sub_forms:
                link = session.first(sa.Select(models.links.LanePoolLink).where(
                    models.links.LanePoolLink.experiment_id == form.experiment.id,
                    models.links.LanePoolLink.lane_num == sample_sub_form.lane.data,
                    models.links.LanePoolLink.pool_id == sample_sub_form.pool_id.data,
                ))
                if link is None:
                    raise exc.NotFoundException(f"Pool {sample_sub_form.pool_id.data} is not on lane {sample_sub_form.lane.data} of this experiment.")

                link.num_m_reads = float(sample_sub_form.m_reads.data)
                if not sample_sub_form.dilution.data or sample_sub_form.dilution.data == "Orig.":
                    link.dilution_id = None
                    sample_sub_form.dilution.data = "Orig."
                else:
                    dilution = session.first(
                        Q.pool_dilution.select(pool_id=link.pool.id, identifier=sample_sub_form.dilution.data)
                    )
                    if dilution is None:
                        raise exc.NotFoundException(f"Dilution '{sample_sub_form.dilution.data}' of pool {link.pool.id} not found.")
                    link.dilution_id = dilution.id

                session.save(link)

                data["lane"].append(link.lane.number)
                data["pool"].append(link.pool.name)
                data["lane_id"].append(link.lane.id)
                data["pool_id"].append(link.pool.id)
                data["num_m_reads"].append(link.num_m_reads)
                data["avg_fragment_size"].append(link.pool.avg_fragment_size)
                data["qubit_concentration"].append(
                    link.dilution.qubit_concentration if link.dilution is not None else link.pool.qubit_concentration
                )
                data["molarity"].append(
                    link.dilution.molarity(link.pool) if link.dilution is not None else link.pool.molarity
                )
                data["target_total_volume"].append(link.lane.total_volume_ul)
                data["target_concentration"].append(link.lane.target_molarity)
                data["dilution"].append(link.dilution.identifier if link.dilution is not None else "Orig.")

            df = pd.DataFrame(data)
            df["share"] = None
            for lane, _df in df.groupby(["lane", "lane_id"]):
                df.loc[_df.index, "share"] = _df["num_m_reads"].values / _df["num_m_reads"].sum()

            df["pipet"] = df["target_concentration"] / df["molarity"] * df["share"] * df["target_total_volume"]

            # Save TSV file
            filename = f"lane_pooling_{form.experiment.id}"
            extension = ".tsv"
            _uuid = uuid7().__str__()
            media_folder = config.settings.app_config.media_folder
            file_dir = C.MediaFileType.LANE_POOLING_TABLE.dir
            filepath = os.path.join(media_folder, file_dir, f"{_uuid}{extension}")

            content = df.to_csv(sep="\t", index=False).encode("utf-8")
            size_bytes = len(content)

            db_file = session.save(Q.media_file.create(
                name=filename,
                uuid=_uuid,
                size_bytes=size_bytes,
                type=C.MediaFileType.LANE_POOLING_TABLE,
                extension=extension,
                uploader_id=current_user.id,
                experiment_id=form.experiment.id,
            ))
            session.save(Q.comment.create(
                author=current_user,
                file=db_file,
                text="Added file for pooling ratios",
                experiment_id=form.experiment.id,
            ))

            # written last, so a failing database change leaves no file behind
            session.flush()
            os.makedirs(os.path.join(media_folder, file_dir), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(content)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Laning Completed!", "success"),
            )
        return route