import json

import pandas as pd
import plotly
import plotly.express as px
import plotly.graph_objects as go
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/plots", tags=["plots"])

_INSIDER = [Depends(dependencies.require_insider)]
_ADMIN = [Depends(dependencies.require_admin)]


class PlotWidthRequest(BaseModel):
    width: float = 1000


def _add_traces(to_figure, from_figure):
    for trace in from_figure.data:
        to_figure.add_trace(trace)
    return to_figure


def _plotly_response(fig) -> Response:
    return Response(
        content=json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder),
        media_type="application/json",
    )


def _entity_tick(route: str, id_param: str, entity_id, label, experiment_id: int) -> str:
    if pd.isna(entity_id):
        return ""
    href = responses.url_for(route, **{id_param: int(entity_id)}).include_query_params(
        **{"from": f"experiment@{experiment_id}"}
    )
    return f"<a href='{href}' target='_self'>{label}</a>"


def _bar_layout(fig, width: float, height: float):
    fig.update_layout(
        width=width,
        height=height,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=15)),
        xaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    return fig


@router.get(
    "/experiment_library_reads/{experiment_id}",
    name="plots_api.experiment_library_reads",
    dependencies=_INSIDER,
)
def experiment_library_reads(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    return responses.htmx_response(
        "components/plots/experiment_library_reads.html",
        experiment=experiment,
    )


@router.post("/experiment_library_reads/{experiment_id}", dependencies=_INSIDER)
def experiment_library_reads_data(
    experiment_id: int,
    body: PlotWidthRequest,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    df = session.pd.get_experiment_seq_qualities(experiment_id)
    if len(df) == 0:
        return responses.htmx_response()

    df["lane"] = df["lane"].astype(str)
    df["num_lane_reads"] = df.groupby("lane")["num_reads"].transform("sum")
    df["perc_reads"] = df["num_reads"] / df["num_lane_reads"]
    mapping = df.groupby("library_id")["num_reads"].sum().to_dict()
    mapping[None] = df.loc[df["library_id"].isna(), "num_reads"].sum()
    df["num_total_library_reads"] = df["library_id"].map(mapping)
    df = df.sort_values(by=["lane", "num_total_library_reads"], ascending=[True, True])

    df["y_ticks"] = df.apply(
        lambda row: _entity_tick(
            "library_page", "library_id", row["library_id"], row["library_name"], experiment.id
        ),
        axis=1,
    )
    df.loc[df["library_id"].isna(), "y_ticks"] = "Undetermined"

    fig = _add_traces(go.Figure(), px.bar(
        df, x="num_reads", y="y_ticks", color="lane",
        text=df["perc_reads"].apply(lambda x: f"{x * 100:.1f} %"),
        labels={
            "num_reads": "# Reads",
            "y_ticks": "Library",
            "lane": "Lane",
            "text": "%-Reads in Lane",
        },
        color_discrete_sequence=px.colors.qualitative.D3,
    ))
    _bar_layout(fig, body.width, 50 * len(df["library_name"].unique()) + 200)
    return _plotly_response(fig)


@router.get(
    "/experiment_pool_reads/{experiment_id}",
    name="plots_api.experiment_pool_reads",
    dependencies=_INSIDER,
)
def experiment_pool_reads(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    return responses.htmx_response(
        "components/plots/experiment_pool_reads.html",
        experiment=experiment,
    )


@router.post("/experiment_pool_reads/{experiment_id}", dependencies=_INSIDER)
def experiment_pool_reads_data(
    experiment_id: int,
    body: PlotWidthRequest,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    df = session.pd.get_experiment_stats(experiment_id)
    if len(df) == 0:
        return responses.htmx_response()

    df = df.groupby(["pool_id", "pool_name"], dropna=False).agg(
        num_reads=pd.NamedAgg(column="num_reads", aggfunc="sum")
    ).reset_index()

    df["perc_reads"] = df["num_reads"] / df["num_reads"].sum()
    df["label"] = df.apply(
        lambda row: f"{row['num_reads'] / 1_000_000:.1f} M ({row['perc_reads'] * 100:.1f} %)",
        axis=1,
    )
    df["y_ticks"] = df.apply(
        lambda row: _entity_tick("pool_page", "pool_id", row["pool_id"], row["pool_name"], experiment.id),
        axis=1,
    )
    df.loc[df["pool_name"].isna(), "y_ticks"] = "Undetermined"
    df = df.sort_values(by=["num_reads"], ascending=[True])

    fig = _add_traces(go.Figure(), px.bar(
        df, x="num_reads", y="y_ticks",
        text=df["label"],
        labels={"y_ticks": "Pool"},
        color_discrete_sequence=px.colors.qualitative.D3,
    ))
    _bar_layout(fig, body.width, 30 * len(df) + 200)
    return _plotly_response(fig)


@router.get(
    "/experiment_pool_per_library_reads/{experiment_id}",
    name="plots_api.experiment_pool_per_library_reads",
    dependencies=_INSIDER,
)
def experiment_pool_per_library_reads(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    return responses.htmx_response(
        "components/plots/experiment_pool_per_library_reads.html",
        experiment=experiment,
    )


@router.post("/experiment_pool_per_library_reads/{experiment_id}", dependencies=_INSIDER)
def experiment_pool_per_library_reads_data(
    experiment_id: int,
    body: PlotWidthRequest,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    df = session.pd.get_experiment_stats(experiment_id)
    if len(df) == 0:
        return responses.htmx_response()

    df["perc_reads"] = df["num_reads"] / df.groupby("pool_id")["num_reads"].transform("sum")
    df["label"] = df.apply(
        lambda row: f"{row['num_reads'] / 1_000_000:.1f} M ({row['perc_reads'] * 100:.1f} %)",
        axis=1,
    )
    df["pool_reads"] = df.groupby("pool_id")["num_reads"].transform("sum")
    df["y_ticks"] = df.apply(
        lambda row: _entity_tick("pool_page", "pool_id", row["pool_id"], row["pool_name"], experiment.id),
        axis=1,
    )
    df.loc[df["pool_name"].isna(), "y_ticks"] = "Undetermined"
    df = df.sort_values(by=["pool_reads", "num_reads"], ascending=[True, False])

    fig = _add_traces(go.Figure(), px.bar(
        df, x="num_reads", y="y_ticks", color="library_name",
        text=df["perc_reads"].apply(lambda x: f"{x * 100:.1f} %"),
        labels={
            "num_reads": "# Reads",
            "y_ticks": "Pool",
            "text": "%-Reads in Lane",
        },
        color_discrete_sequence=px.colors.qualitative.D3,
    ))
    _bar_layout(fig, body.width, 30 * len(df["pool_id"].unique()) + 200)
    return _plotly_response(fig)


@router.get("/weekday_usage", name="plots_api.weekday_usage", dependencies=_ADMIN)
def weekday_usage():
    return responses.htmx_response("components/plots/weekday_usage.html")


@router.post("/weekday_usage", dependencies=_ADMIN)
def weekday_usage_data(body: PlotWidthRequest):
    return responses.htmx_response()
