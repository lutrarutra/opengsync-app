from typing import TYPE_CHECKING
import json

from flask import Blueprint, request, abort, url_for
from flask_login import login_required
from flask_htmx import make_response

import plotly
import plotly.express as px
import plotly.graph_objects as go

from opengsync_db import models
from opengsync_db.categories import HTTPResponse
from .... import db, htmx_route

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

plots_api = Blueprint("plots_api", __name__, url_prefix="/api/plots/")


def _add_traces(to_figure, from_figure):
    for trace in from_figure.data:
        to_figure.add_trace(trace)

    return to_figure


@htmx_route(plots_api, db=db, methods=["POST"])
def experiment_library_reads(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    request_args = request.get_json()
    width = request_args.get("width", 700)
    
    df = db.get_experiment_seq_qualities_df(experiment_id)
    if len(df) == 0:
        return make_response()

    df["lane"] = df["lane"].astype(str)
    df["perc_reads"] = df["num_library_reads"] / df["num_lane_reads"]
    mapping = df.groupby("library_id")["num_library_reads"].sum().to_dict()
    df["num_total_library_reads"] = df["library_id"].map(mapping)
    df = df.sort_values(by=["lane", "num_total_library_reads"], ascending=[True, True])

    df["y_ticks"] = df.apply(lambda row: f"<a href='{url_for('libraries_page.library', library_id=row['library_id'])}?from=experiment@{experiment.id}' target='_self'>{row['library_name']}</a>", axis=1)
    df.loc[df["library_id"] == -1, "y_ticks"] = "Undetermined"

    fig = go.Figure()

    barplot = px.bar(
        df, x="num_library_reads", y="y_ticks", color="lane", barmode="group",
        text=df["perc_reads"].apply(lambda x: f"{x * 100:.1f} %"),
        labels={
            "num_library_reads": "# Reads",
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
    
