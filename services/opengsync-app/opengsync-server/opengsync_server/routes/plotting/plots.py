import json
import pandas as pd
import numpy as np

import sqlalchemy as sa
from flask import Blueprint, request, url_for, render_template
from flask_htmx import make_response

import plotly
import plotly.express as px
import plotly.graph_objects as go

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions, runtime

plots_api = Blueprint("plots_api", __name__, url_prefix="/plots/")


def _add_traces(to_figure, from_figure):
    for trace in from_figure.data:
        to_figure.add_trace(trace)

    return to_figure


@wrappers.htmx_route(plots_api, db=db, methods=["GET", "POST"])
def experiment_library_reads(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.BadRequestException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return make_response(render_template(
            "components/plots/experiment_library_reads.html",
            experiment=experiment
        ))
    
    request_args = request.get_json()
    width = request_args.get("width", 700)
    
    df = db.pd.get_experiment_seq_qualities(experiment_id)
    if len(df) == 0:
        return make_response()
    
    df["lane"] = df["lane"].astype(str)
    df["num_lane_reads"] = df.groupby("lane")["num_reads"].transform("sum")
    df["perc_reads"] = df["num_reads"] / df["num_lane_reads"]
    mapping = df.groupby("library_id")["num_reads"].sum().to_dict()
    mapping[None] = df.loc[df["library_id"].isna(), "num_reads"].sum()
    df["num_total_library_reads"] = df["library_id"].map(mapping)
    df = df.sort_values(by=["lane", "num_total_library_reads"], ascending=[True, True])

    df["y_ticks"] = df.apply(
        lambda row: f"<a href='{url_for('libraries_page.library', library_id=row['library_id'])}?from=experiment@{experiment.id}' target='_self'>{row['library_name']}</a>"
        if pd.notna(row["library_id"]) else "", axis=1  # type: ignore
    )
    
    df.loc[df["library_id"].isna(), "y_ticks"] = "Undetermined"

    fig = go.Figure()

    barplot = px.bar(
        df, x="num_reads", y="y_ticks", color="lane",
        text=df["perc_reads"].apply(lambda x: f"{x * 100:.1f} %"),
        labels={
            "num_reads": "# Reads",
            "y_ticks": "Library",
            "lane": "Lane",
            "text": "%-Reads in Lane"
        },
        color_discrete_sequence=px.colors.qualitative.D3
    )
    fig = _add_traces(barplot, fig)
    fig.update_layout(
        width=width,
        height=20 * len(df) + 200,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=15)),
        xaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


@wrappers.htmx_route(plots_api, db=db, methods=["GET", "POST"])
def experiment_pool_reads(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.BadRequestException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return make_response(render_template(
            "components/plots/experiment_pool_reads.html",
            experiment=experiment
        ))
    
    request_args = request.get_json()
    width = request_args.get("width", 700)
    
    df = db.pd.get_experiment_stats(experiment_id)
    if len(df) == 0:
        return make_response()
    
    df = df.groupby(["pool_id", "pool_name"], dropna=False).agg(
        num_reads=pd.NamedAgg(column="num_reads", aggfunc="sum")
    ).reset_index()

    df["perc_reads"] = df["num_reads"] / df["num_reads"].sum()

    df["label"] = df.apply(
        lambda row: f"{row['num_reads'] / 1_000_000:.1f} M ({row['perc_reads'] * 100:.1f} %)", axis=1
    )

    df["y_ticks"] = df.apply(
        lambda row: f"<a href='{url_for('pools_page.pool', pool_id=row['pool_id'])}?from=experiment@{experiment.id}' target='_self'>{row['pool_name']}</a>"
        if pd.notna(row["pool_id"]) else "", axis=1  # type: ignore
    )
    df.loc[df["pool_name"].isna(), "y_ticks"] = "Undetermined"

    df = df.sort_values(by=["num_reads"], ascending=[True])
    
    fig = go.Figure()

    barplot = px.bar(
        df, x="num_reads", y="y_ticks",
        text=df["label"],
        labels={
            "y_ticks": "Pool",
        },
        color_discrete_sequence=px.colors.qualitative.D3
    )
    fig = _add_traces(barplot, fig)
    fig.update_layout(
        width=width,
        height=30 * len(df) + 200,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=15)),
        xaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


@wrappers.htmx_route(plots_api, db=db, methods=["GET", "POST"])
def experiment_pool_per_library_reads(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.BadRequestException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    if request.method == "GET":
        return make_response(render_template(
            "components/plots/experiment_pool_per_library_reads.html",
            experiment=experiment
        ))
    
    request_args = request.get_json()
    width = request_args.get("width", 700)
    
    df = db.pd.get_experiment_stats(experiment_id)
    if len(df) == 0:
        return make_response()

    df["perc_reads"] = df["num_reads"] / df.groupby("pool_id")["num_reads"].transform("sum")

    df["label"] = df.apply(
        lambda row: f"{row['num_reads'] / 1_000_000:.1f} M ({row['perc_reads'] * 100:.1f} %)", axis=1
    )

    df["pool_reads"] = df.groupby("pool_id")["num_reads"].transform("sum")

    df["y_ticks"] = df.apply(
        lambda row: f"<a href='{url_for('pools_page.pool', pool_id=row['pool_id'])}?from=experiment@{experiment.id}' target='_self'>{row['pool_name']}</a>"
        if pd.notna(row["pool_id"]) else "", axis=1  # type: ignore
    )
    df.loc[df["pool_name"].isna(), "y_ticks"] = "Undetermined"

    df = df.sort_values(by=["pool_reads", "num_reads"], ascending=[True, False])
    
    fig = go.Figure()

    barplot = px.bar(
        df, x="num_reads", y="y_ticks", color="library_name",
        text=df["perc_reads"].apply(lambda x: f"{x * 100:.1f} %"),
        labels={
            "num_reads": "# Reads",
            "y_ticks": "Pool",
            "text": "%-Reads in Lane"
        },
        color_discrete_sequence=px.colors.qualitative.D3
    )
    fig = _add_traces(barplot, fig)
    fig.update_layout(
        width=width,
        height=30 * len(df["pool_id"].unique()) + 200,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=15)),
        xaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    

@wrappers.htmx_route(plots_api, db=db, methods=["GET", "POST"])
def weekday_usage(current_user: models.User):
    if not current_user.is_admin:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return make_response(render_template(
            "components/plots/weekday_usage.html"
        ))
    
    request_args = request.get_json()
    width = request_args.get("width", 700)

    from ... import monitor
    
    runtime.app.performance_monitor.open_session()
    now = pd.Timestamp.now(tz="UTC")
    this_monday = now - pd.Timedelta(days=now.weekday())
    this_monday = this_monday.normalize()  # Strips time to 00:00:00
    query = sa.select(monitor.RequestStat).where(
        monitor.RequestStat.timestamp_utc >= this_monday
    )
    df = pd.read_sql(query, runtime.app.performance_monitor._engine)
    runtime.app.performance_monitor.close_session(commit=False)
    df["timestamp"] = pd.to_datetime(df["timestamp_utc"]).dt.tz_convert("Europe/Vienna")
    df.tail()
    if len(df) == 0:
        return make_response()
    
    df["timestamp"] = pd.to_datetime(df["timestamp_utc"]).dt.tz_convert("Europe/Vienna")
    df["weekday"] = df["timestamp"].dt.weekday  # type: ignore
    df["hour"] = df["timestamp"].dt.hour  # type: ignore

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    full_index = pd.MultiIndex.from_product([range(0, 7), np.arange(24)], names=["weekday", "hour"])  # type: ignore

    usage_matrix = df.groupby(['weekday', 'hour']).size()
    usage_matrix = usage_matrix.reindex(full_index, fill_value=0).unstack(level='hour')

    import plotly.express as px

    fig = px.imshow(
        usage_matrix.values.T,
        labels=dict(x="Weekday", y="Hour", color="Requests"),
        x=weekdays,
        y=usage_matrix.columns.astype(str),  # weekdays as strings for better axis display
        aspect="auto",
        color_continuous_scale="tempo",
    )

    fig.update_layout(
        width=width,
        height=400,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickfont=dict(size=15)),
        yaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)