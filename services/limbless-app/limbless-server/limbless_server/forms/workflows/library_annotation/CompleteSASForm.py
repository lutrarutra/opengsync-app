import os
import shutil
from typing import Optional

import pandas as pd

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response

from limbless_db import models, DBSession
from limbless_db.categories import GenomeRef, LibraryType, FeatureType, FileType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm


class CompleteSASForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-11.html"
    _form_label = "complete_sas_form"

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)

    def prepare(self):
        library_table = self.tables["library_table"]
        project_table = self.tables["project_table"]
        pool_table = self.tables.get("pool_table")
        feature_table = self.tables.get("feature_table")
        cmo_table = self.tables.get("cmo_table")
        visium_table = self.tables.get("visium_table")
        comment_table = self.tables.get("comment_table")

        sample_table = self.get_sample_table(library_table, project_table, cmo_table)

        self._context["library_table"] = library_table
        self._context["pool_table"] = pool_table
        self._context["feature_table"] = feature_table
        self._context["cmo_table"] = cmo_table
        self._context["visium_table"] = visium_table
        self._context["comment_table"] = comment_table
        self._context["sample_table"] = sample_table

        input_type = "raw" if "pool" not in library_table.columns else "pooled"

        LINK_WIDTH_UNIT = 1
        nodes = []
        links = []
        node_idx = 0

        project_nodes = {}
        pool_nodes = {}

        for (sample_name, project), _df in library_table.groupby(["sample_name", "project"]):
            sample_pool = []
            if (project_node := project_nodes.get(project)) is None:
                project_node = {
                    "node": node_idx,
                    "name": project_table[project_table["project"] == project].iloc[0]["name"],
                }
                project_nodes[project] = project_node
                nodes.append(project_node)
                node_idx += 1

            for _, row in sample_table[sample_table["sample_pool"] == sample_name].iterrows():
                sample_node = {
                    "node": node_idx,
                    "name": row["sample_name"],
                }
                sample_pool.append(sample_node)
                nodes.append(sample_node)
                node_idx += 1

                links.append({
                    "source": project_node["node"],
                    "target": sample_node["node"],
                    "value": LINK_WIDTH_UNIT * len(library_table[library_table["sample_name"] == sample_name]),
                })

            for _, row in _df.iterrows():
                library_node = {
                    "node": node_idx,
                    "name": f"{row['library_name']} - {LibraryType.get(row['library_type_id']).abbreviation}",
                }
                nodes.append(library_node)
                node_idx += 1
                for sample_node in sample_pool:
                    links.append({
                        "source": sample_node["node"],
                        "target": library_node["node"],
                        "value": LINK_WIDTH_UNIT,
                    })
                if input_type == "raw":
                    continue
                
                if (pool_node := pool_nodes.get(row["pool"])) is None:
                    pool_node = {
                        "node": node_idx,
                        "name": row["pool"],
                    }
                    nodes.append(pool_node)
                    node_idx += 1
                    pool_nodes[row["pool"]] = pool_node

                links.append({
                    "source": library_node["node"],
                    "target": pool_node["node"],
                    "value": LINK_WIDTH_UNIT * len(sample_pool),
                })

        self._context["nodes"] = nodes
        self._context["links"] = links

    def get_sample_table(self, library_table: pd.DataFrame, project_table: pd.DataFrame, cmo_table: Optional[pd.DataFrame]) -> pd.DataFrame:
        sample_data = {
            "sample_name": [],
            "sample_pool": [],
            "project_label": [],
            "project_name": [],
            "sample_id": [],
            "project_id": [],
            "library_types": [],
            "is_cmo_sample": [],
            "sequence": [],
            "pattern": [],
            "read": [],
        }

        def add_sample(
            sample_name: str,
            sample_pool: str,
            project_label: str,
            project_name: str,
            project_id: str,
            is_cmo_sample: bool,
            library_types: list[str],
            sample_id: Optional[int] = None,
            sequence: Optional[str] = None,
            pattern: Optional[str] = None,
            read: Optional[str] = None,
        ):
            sample_data["sample_name"].append(sample_name)
            sample_data["sample_pool"].append(sample_pool)
            sample_data["project_label"].append(project_label)
            sample_data["project_name"].append(project_name)
            sample_data["project_id"].append(project_id)
            sample_data["sample_id"].append(sample_id)
            sample_data["library_types"].append(library_types)
            sample_data["is_cmo_sample"].append(is_cmo_sample)
            sample_data["sequence"].append(sequence)
            sample_data["pattern"].append(pattern)
            sample_data["read"].append(read)

        for (sample_name, sample_id, project, is_cmo_sample), _df in library_table.groupby(["sample_name", "sample_id", "project", "is_cmo_sample"], dropna=False):
            library_types = [LibraryType.get(library_type_id).abbreviation for library_type_id in _df["library_type_id"].unique()]
            project_row = project_table[project_table["project"] == project].iloc[0]
            if not is_cmo_sample:
                add_sample(
                    sample_name=sample_name,
                    sample_pool=sample_name,
                    project_label=project_row["project"],
                    project_name=project_row["name"],
                    sample_id=sample_id,
                    project_id=project_row["id"],
                    library_types=library_types,
                    is_cmo_sample=False
                )
            else:
                if cmo_table is None:
                    logger.error(f"{self.uuid}: CMO reference table not found.")
                    raise Exception("CMO reference should not be None.")
                
                for _, cmo_row in cmo_table[cmo_table["sample_name"] == sample_name].iterrows():
                    add_sample(
                        sample_name=cmo_row["demux_name"],
                        sample_pool=sample_name,
                        project_label=project_row["project"],
                        project_name=project_row["name"],
                        project_id=project_row["id"],
                        library_types=library_types,
                        is_cmo_sample=True,
                        sequence=cmo_row["sequence"],
                        pattern=cmo_row["pattern"],
                        read=cmo_row["read"],
                    )

        return pd.DataFrame(sample_data)
    
    def __update_data(
        self, sample_table: pd.DataFrame, library_table: pd.DataFrame, project_table: pd.DataFrame,
        pool_table: Optional[pd.DataFrame], visium_table: Optional[pd.DataFrame],
        cmo_table: Optional[pd.DataFrame]
    ):
        self.add_table("sample_table", sample_table)
        self.update_table("library_table", library_table, False)
        self.update_table("project_table", project_table, False)
        if pool_table is not None:
            self.update_table("pool_table", pool_table, False)
        if visium_table is not None:
            self.update_table("visium_table", visium_table, False)
        if cmo_table is not None:
            self.update_table("cmo_table", cmo_table, False)

        self.update_data()

    def process_request(self, **context) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response(**context)
        
        user: models.User = context["user"]
        seq_request: models.SeqRequest = context["seq_request"]

        library_table = self.tables["library_table"]
        project_table = self.tables["project_table"]
        pool_table = self.tables.get("pool_table")
        feature_table = self.tables.get("feature_table")
        cmo_table = self.tables.get("cmo_table")
        visium_table = self.tables.get("visium_table")
        comment_table = self.tables.get("comment_table")

        sample_table = self.get_sample_table(library_table, project_table, cmo_table)

        if current_app.debug:
            self.__update_data(
                sample_table=sample_table,
                library_table=library_table,
                project_table=project_table,
                pool_table=pool_table,
                visium_table=visium_table,
                cmo_table=cmo_table
            )

        if visium_table is not None:
            visium_table["id"] = None
            with DBSession(db) as session:
                for idx, visium_row in visium_table.iterrows():
                    visium_annotation = db.create_visium_annotation(
                        area=visium_row["area"],
                        image=visium_row["image"],
                        slide=visium_row["slide"],
                    )
                    visium_table.at[idx, "id"] = visium_annotation.id

            visium_table["id"] = visium_table["id"].astype(int)

        with DBSession(db) as session:
            for idx, row in project_table.iterrows():
                if pd.isna(row["id"]):
                    project = session.create_project(
                        name=row["name"],
                        description="",
                        owner_id=user.id
                    )
                    project_table.at[idx, "id"] = project.id
                    sample_table.loc[sample_table["project_label"] == row["project"], "project_id"] = project.id

            project_table["id"] = project_table["id"].astype(int)

        with DBSession(db) as session:
            sample_table["cmo_id"] = None
            for idx, row in sample_table.iterrows():
                if pd.isna(row["sample_id"]):
                    sample = session.create_sample(
                        name=row["sample_name"],
                        project_id=row["project_id"],
                        owner_id=user.id
                    )
                    sample_table.at[idx, "sample_id"] = sample.id
                if row["is_cmo_sample"]:
                    cmo = session.create_cmo(
                        sequence=row["sequence"],
                        pattern=row["pattern"],
                        read=row["read"],
                    )
                    sample_table.at[idx, "cmo_id"] = cmo.id

            sample_table["sample_id"] = sample_table["sample_id"].astype(int)

        if pool_table is not None:
            pool_table["pool_id"] = None
            with DBSession(db) as session:
                for idx, row in pool_table.iterrows():
                    pool = session.create_pool(
                        name=row["name"],
                        owner_id=user.id,
                        seq_request_id=seq_request.id,
                        num_m_reads_requested=row["num_m_reads"],
                        contact_name=row["contact_person_name"],
                        contact_email=row["contact_person_email"],
                        contact_phone=row["contact_person_phone"] if pd.notna(row["contact_person_phone"]) else None,
                    )
                    pool_table.at[idx, "pool_id"] = pool.id

            logger.debug(pool_table.dtypes)
            pool_table["pool_id"] = pool_table["pool_id"].astype(int)
            logger.debug(pool_table.dtypes)

        with DBSession(db) as session:
            library_table["library_id"] = None
            for idx, row in library_table.iterrows():
                if visium_table is not None:
                    visium_row = visium_table[visium_table["library_name"] == row["library_name"]].iloc[0]
                    visium_annotation_id = int(visium_row["id"])
                else:
                    visium_annotation_id = None

                if pool_table is not None:
                    pool_row = pool_table[pool_table["name"] == row["pool"]].iloc[0]
                    pool_id = int(pool_row["pool_id"])
                else:
                    pool_id = None

                library = session.create_library(
                    name=row["library_name"],
                    seq_request_id=seq_request.id,
                    library_type=LibraryType.get(row["library_type_id"]),
                    owner_id=user.id,
                    genome_ref=GenomeRef.get(row["genome_id"]),
                    index_1_sequence=row["index_1"].strip() if pd.notna(row["index_1"]) else None,
                    index_2_sequence=row["index_2"].strip() if pd.notna(row["index_2"]) else None,
                    index_3_sequence=row["index_3"].strip() if pd.notna(row["index_3"]) else None,
                    index_4_sequence=row["index_4"].strip() if pd.notna(row["index_4"]) else None,
                    adapter=row["adapter"].strip() if pd.notna(row["adapter"]) else None,
                    visium_annotation_id=visium_annotation_id,
                    pool_id=pool_id,
                    seq_depth_requested=row["seq_depth"] if "seq_depth" in row and pd.notna(row["seq_depth"]) else None,
                )
                library_table.at[idx, "library_id"] = library.id
                library_samples = sample_table[sample_table["sample_pool"] == row["sample_name"]]
                for idx, sample_row in library_samples.iterrows():
                    session.link_sample_library(
                        sample_id=sample_row["sample_id"],
                        library_id=library.id,
                        cmo_id=sample_row["cmo_id"]
                    )

            library_table["library_id"] = library_table["library_id"].astype(int)

        if feature_table is not None:
            custom_features = feature_table[feature_table["feature_id"].isna()]
            with DBSession(db) as session:
                for (feature, pattern, read, sequence), _df in custom_features.groupby(["feature", "pattern", "read", "sequence"]):
                    feature = session.create_feature(
                        name=feature,
                        sequence=sequence,
                        pattern=pattern,
                        read=read,
                        type=FeatureType.ANTIBODY
                    )
                    feature_id = feature.id
                    feature_table.loc[_df.index, "feature_id"] = feature_id

            with DBSession(db) as session:
                for _, feature_row in feature_table.iterrows():
                    libraries = library_table[library_table["library_name"] == feature_row["library_name"]]
                    for _, library_row in libraries.iterrows():
                        session.link_feature_library(
                            feature_id=feature_row["feature_id"],
                            library_id=library_row["library_id"]
                        )

            feature_table["feature_id"] = feature_table["feature_id"].astype(int)
            
        if comment_table is not None:
            for _, row in comment_table.iterrows():
                comment = session.create_comment(
                    text=row["text"],
                    author_id=user.id,
                )
                session.add_seq_request_comment(
                    seq_request_id=seq_request.id,
                    comment_id=comment.id
                )

        self.__update_data(
            sample_table=sample_table,
            library_table=library_table,
            project_table=project_table,
            pool_table=pool_table,
            visium_table=visium_table,
            cmo_table=cmo_table
        )

        flash(f"Added {library_table.shape[0]} libraries to sequencing request.", "success")

        newdir = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_ANNOTATION.dir, str(seq_request.id))
        os.makedirs(newdir, exist_ok=True)
        shutil.copy(self.path, os.path.join(newdir, f"{self.uuid}.tsv"))
        os.remove(self.path)

        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))