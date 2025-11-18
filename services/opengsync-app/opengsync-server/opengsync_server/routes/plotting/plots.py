import json
import pandas as pd

from flask import Blueprint, request, url_for, render_template
from flask_htmx import make_response

import plotly
import plotly.express as px
import plotly.graph_objects as go

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions

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
        df, x="num_reads", y="y_ticks", color="lane", barmode="group",
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
        height=40 * len(df) + 200,
        margin=dict(t=25, r=5, b=5, l=5),
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=15)),
        xaxis=dict(tickfont=dict(size=15)),
        font=dict(size=15),
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
