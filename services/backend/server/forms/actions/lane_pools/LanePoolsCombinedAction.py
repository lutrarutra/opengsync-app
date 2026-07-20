import os
from uuid6 import uuid7

import pandas as pd
import sqlalchemy as sa
from fastapi import Depends
from sqlalchemy import orm
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses, config
from ....components import inputs
from ....utils import parsing
from ...HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm

DEFAULT_TARGET_NM = 3.0
DEFAULT_TOTAL_VOLUME_TARGET = 50.0


class LanedPoolRowSchema(BaseModel):
    lane: int
    pool_id: int
    lane_id: int
    num_m_reads: float | None
    qubit_concentration: float | None
    avg_fragment_size: int | None


class SampleSubForm(SubHTMXForm):
    pool_id = inputs.numeric.IntInputField("Pool ID", required=True, read_only=True)
    m_reads = inputs.numeric.FloatInputField("M Reads", required=True, ge=0.0)
    dilution = inputs.string.StringInputField("Dilution", required=False)


class LanePoolsCombinedAction(HTMXForm):
    template_path = "workflows/experiment/lane_pools-1.2.html"

    sample_sub_forms = inputs.dynamic.SubFormList[SampleSubForm](min_elements=1)
    target_total_volume = inputs.numeric.FloatInputField(
        "Target Total Volume (µL)", required=True, default=DEFAULT_TOTAL_VOLUME_TARGET, ge=0.0
    )
    target_molarity = inputs.numeric.FloatInputField(
        "Target Molarity (nM)", required=True, default=DEFAULT_TARGET_NM, ge=0.0
    )

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
        ) -> "LanePoolsCombinedAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
                orm.selectinload(models.Experiment.pools).selectinload(models.Pool.lane_links).selectinload(models.links.LanePoolLink.lane)
            ))
            if not experiment.workflow.combined_lanes:
                raise exc.OpeNGSyncServerException("This experiment uses a separate lane workflow, not a combined lane workflow.")
            return cls(experiment=experiment)
        return dependency

    @htmx_route("GET", "/{experiment_id}/lane-pools")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LanePoolsCombinedAction" = Depends(LanePoolsCombinedAction.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            df = session.pd.get_experiment_laned_pools(form.experiment.id)
            df["original_qubit_concentration"] = df["qubit_concentration"]
            df["dilutions"] = None
            df = df.drop(columns=["lane"]).drop_duplicates(subset=["pool_id"]).reset_index(drop=True)

            for idx, row in parsing.safe_iter(df, LanedPoolRowSchema):
                sample_sub = form.sample_sub_forms.append_entry()

                sample_sub.pool_id.data = row.pool_id
                sample_sub.m_reads._data = row.num_m_reads * form.experiment.num_lanes if row.num_m_reads is not None else None

                pool = session.get_one(Q.pool.select(id=row.pool_id))
                df.at[idx, "dilutions"] = [("Orig.", pool.qubit_concentration, pool.molarity, "")]  # type: ignore

                for dilution in pool.dilutions:
                    sample_sub.dilution.data = dilution.identifier
                    df.at[idx, "dilutions"].append((dilution.identifier, dilution.qubit_concentration, dilution.molarity(pool), dilution.timestamp_str()))  # type: ignore
                    df.at[idx, "qubit_concentration"] = dilution.qubit_concentration

            df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
            df["share"] = df["num_m_reads"] / df["num_m_reads"].sum()

            df["molarity_color"] = "cemm-green"
            df.loc[df["molarity"] < models.Pool.warning_min_molarity, "molarity_color"] = "cemm-yellow"
            df.loc[df["molarity"] > models.Pool.warning_max_molarity, "molarity_color"] = "cemm-yellow"
            df.loc[df["molarity"] < models.Pool.error_min_molarity, "molarity_color"] = "cemm-red"
            df.loc[df["molarity"] > models.Pool.error_max_molarity, "molarity_color"] = "cemm-red"

            df["pipet"] = DEFAULT_TARGET_NM / df["molarity"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET

            form._context["df"] = df
            form._context["enumerate"] = enumerate

            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/lane-pools")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LanePoolsCombinedAction" = Depends(LanePoolsCombinedAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
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
                "dilution": [],
            }

            for lane in form.experiment.lanes:
                lane.target_molarity = form.target_molarity.data
                lane.total_volume_ul = form.target_total_volume.data
                session.save(lane)

                for sample_sub_form in form.sample_sub_forms:
                    link = session.get_one(sa.Select(models.links.LanePoolLink).where(
                        models.links.LanePoolLink.experiment_id == form.experiment.id,
                        models.links.LanePoolLink.lane_num == lane.number,
                        models.links.LanePoolLink.pool_id == sample_sub_form.pool_id.data,
                    ))

                    link.num_m_reads = sample_sub_form.m_reads.data / form.experiment.num_lanes
                    if not sample_sub_form.dilution.data or sample_sub_form.dilution.data == "Orig.":
                        sample_sub_form.dilution.data = "Orig."
                        link.dilution_id = None
                    else:
                        dilution = session.get_one(
                            Q.pool_dilution.select(pool_id=link.pool.id, identifier=sample_sub_form.dilution.data)
                        )
                        link.dilution_id = dilution.id

                    session.save(link)

                    data["lane"].append(lane.number)
                    data["pool"].append(link.pool.name)
                    data["lane_id"].append(lane.id)
                    data["pool_id"].append(link.pool.id)
                    data["num_m_reads"].append(link.num_m_reads)
                    data["avg_fragment_size"].append(link.pool.avg_fragment_size)
                    data["qubit_concentration"].append(
                        link.dilution.qubit_concentration if link.dilution else link.pool.qubit_concentration
                    )
                    data["target_total_volume"].append(form.target_total_volume.data)
                    data["target_concentration"].append(form.target_molarity.data)
                    data["dilution"].append(link.dilution.identifier if link.dilution else "Orig.")

            df = pd.DataFrame(data)
            df["share"] = None
            for _, _df in df.groupby("lane"):
                df.loc[_df.index, "share"] = _df["num_m_reads"] / _df["num_m_reads"].sum()
            df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
            df["pipet"] = df["target_concentration"] / df["molarity"] * df["share"] * df["target_total_volume"]

            # Save TSV file
            filename = f"lane_pooling_{form.experiment.id}"
            extension = ".tsv"
            _uuid = uuid7().__str__()
            media_folder = config.settings.app_config.media_folder
            file_dir = C.MediaFileType.LANE_POOLING_TABLE.dir
            filepath = os.path.join(media_folder, file_dir, f"{_uuid}{extension}")

            os.makedirs(os.path.join(media_folder, file_dir), exist_ok=True)
            df.to_csv(filepath, sep="\t", index=False)
            size_bytes = os.stat(filepath).st_size

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

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Laning Completed!", "success"),
            )
        return route