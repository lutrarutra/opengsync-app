import os
import shutil
from typing import Optional

import pandas as pd
import numpy as np

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response

from limbless_db import models, DBSession
from limbless_db.categories import GenomeRef, LibraryType, FeatureType, FileType, SampleStatus, PoolType, AttributeType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm


class CompleteSASForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-complete.html"
    _form_label = "complete_sas_form"

    def __init__(self, seq_request: models.SeqRequest, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def prepare(self):
        library_table = self.tables["library_table"]
        sample_table = self.tables["sample_table"]
        feature_table = self.tables.get("feature_table")
        cmo_table = self.tables.get("cmo_table")
        visium_table = self.tables.get("visium_table")
        flex_table = self.tables.get("flex_table")
        comment_table = self.tables.get("comment_table")

        self._context["library_table"] = library_table
        self._context["sample_table"] = sample_table
        self._context["feature_table"] = feature_table
        self._context["cmo_table"] = cmo_table
        self._context["visium_table"] = visium_table
        self._context["flex_table"] = flex_table
        self._context["comment_table"] = comment_table

        input_type = "raw" if "pool" not in library_table.columns else "pooled"

        LINK_WIDTH_UNIT = 1
        nodes = []
        links = []

        project_node = {
            "node": 0,
            "name": self.metadata["project_name"],
        }
        nodes.append(project_node)
        node_idx = 1
        pool_nodes = {}

        for sample_name, _df in library_table.groupby("sample_name"):
            sample_pool = []
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
                    "name": f"{LibraryType.get(row['library_type_id']).abbreviation} - {row['library_name']}",
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
    
    def __update_data(
        self, sample_table: pd.DataFrame, library_table: pd.DataFrame,
        visium_table: Optional[pd.DataFrame], cmo_table: Optional[pd.DataFrame]
    ):
        self.update_table("sample_table", sample_table, False)
        self.update_table("library_table", library_table, False)
        if visium_table is not None:
            self.update_table("visium_table", visium_table, False)
        if cmo_table is not None:
            self.update_table("cmo_table", cmo_table, False)

        self.update_data()

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response()

        library_table = self.tables["library_table"]
        sample_table = self.tables["sample_table"]
        feature_table = self.tables.get("feature_table")
        cmo_table = self.tables.get("cmo_table")
        visium_table = self.tables.get("visium_table")
        comment_table = self.tables.get("comment_table")

        if current_app.debug:
            self.__update_data(
                sample_table=sample_table,
                library_table=library_table,
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

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.get_project(project_id)) is None:
                logger.error(f"{self.uuid}: Project with id {project_id} not found.")
                raise ValueError(f"Project with id {project_id} not found.")
        else:
            project = db.create_project(
                name=self.metadata["project_name"],
                description=self.metadata["project_description"],
                owner_id=user.id
            )

        with DBSession(db) as session:
            predefined_attrs = [f"_attr_{attr.label}" for attr in AttributeType.as_list()]
            custom_sample_attributes = [attr for attr in sample_table.columns if attr.startswith("_attr_") and attr not in predefined_attrs]
            logger.debug(custom_sample_attributes)
            for idx, row in sample_table.iterrows():
                if pd.notna(row["sample_id"]):
                    if (sample := session.get_sample(row["sample_id"])) is None:
                        logger.error(f"{self.uuid}: Sample with id {row['sample_id']} not found.")
                        raise ValueError(f"Sample with id {row['sample_id']} not found.")
                else:
                    sample = session.create_sample(
                        name=row["sample_name"],
                        project_id=project.id,
                        owner_id=user.id,
                        status=SampleStatus.DRAFT
                    )
                    sample_table.at[idx, "sample_id"] = sample.id

                for attr in AttributeType.as_list():
                    attr_label = f"_attr_{attr.label}"
                    if attr_label in row.keys() and pd.notna(row[attr_label]):
                        sample = session.set_sample_attribute(
                            sample_id=sample.id,
                            type=attr,
                            value=row[attr_label],
                            name=None
                        )

                for attr_label in custom_sample_attributes:
                    if attr_label in row.keys() and pd.notna(row[attr_label]):
                        sample = session.set_sample_attribute(
                            sample_id=sample.id,
                            type=AttributeType.CUSTOM,
                            value=row[attr_label],
                            name=attr_label.removeprefix("_attr_")
                        )

        sample_table["sample_id"] = sample_table["sample_id"].astype(int)

        if self.metadata["workflow_type"] == "pooled":
            if (pool_id := self.metadata["existing_pool_id"]) is not None:
                if (pool := db.get_pool(pool_id)) is None:
                    logger.error(f"{self.uuid}: Pool with id {pool_id} not found.")
                    raise ValueError(f"Pool with id {pool_id} not found.")
            else:
                pool = db.create_pool(
                    name=self.metadata["pool_name"],
                    owner_id=user.id,
                    seq_request_id=self.seq_request.id,
                    pool_type=PoolType.EXTERNAL,
                    contact_email=self.metadata["pool_contact_email"],
                    contact_name=self.metadata["pool_contact_name"],
                    contact_phone=self.metadata["pool_contact_phone"],
                    num_m_reads_requested=self.metadata["pool_num_m_reads_requested"]
                )
        else:
            pool = None

        with DBSession(db) as session:
            library_table["library_id"] = None
            for idx, row in library_table.iterrows():
                if visium_table is not None:
                    visium_row = visium_table[visium_table["library_name"] == row["library_name"]].iloc[0]
                    visium_annotation_id = int(visium_row["id"])
                else:
                    visium_annotation_id = None

                library = session.create_library(
                    name=row["library_name"],
                    seq_request_id=self.seq_request.id,
                    library_type=LibraryType.get(row["library_type_id"]),
                    owner_id=user.id,
                    genome_ref=GenomeRef.get(row["genome_id"]),
                    visium_annotation_id=visium_annotation_id,
                    pool_id=pool.id if pool is not None else None,
                    seq_depth_requested=row["seq_depth"] if "seq_depth" in row and pd.notna(row["seq_depth"]) else None,
                )

                library_table.at[idx, "library_id"] = library.id
                
                if self.metadata["workflow_type"] == "pooled":
                    index_i7_seqs = row["index_i7_sequences"].split(";")
                    index_i5_seqs = row["index_i5_sequences"].split(";") if pd.notna(row["index_i5_sequences"]) else None

                    for i in range(len(index_i7_seqs)):
                        index_i7_seq = index_i7_seqs[i]
                        index_i5_seq = index_i5_seqs[i] if index_i5_seqs is not None and len(index_i5_seqs) > i else None
                        library = session.add_library_index(
                            library_id=library.id,
                            sequence_i7=index_i7_seq,
                            sequence_i5=index_i5_seq if pd.notna(index_i5_seq) else None,
                            name_i7=row["index_i7_name"] if pd.notna(row["index_i7_name"]) else None,
                            name_i5=row["index_i5_name"] if pd.notna(row["index_i5_name"]) else None,
                        )

                library_samples = sample_table[sample_table["sample_pool"] == row["sample_name"]]
                for idx, sample_row in library_samples.iterrows():
                    session.link_sample_library(
                        sample_id=sample_row["sample_id"],
                        library_id=library.id,
                        cmo_sequence=sample_row["cmo_sequence"] if pd.notna(sample_row["cmo_sequence"]) else None,
                        cmo_pattern=sample_row["cmo_pattern"] if pd.notna(sample_row["cmo_pattern"]) else None,
                        cmo_read=sample_row["cmo_read"] if pd.notna(sample_row["cmo_read"]) else None,
                        flex_barcode=sample_row["flex_barcode"] if pd.notna(sample_row["flex_barcode"]) else None,
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
                if row["context"] == "visium_instructions":
                    comment = session.create_comment(
                        text=f"Visium data instructions: {row['text']}",
                        author_id=user.id,
                    )
                elif row["context"] == "custom_genome_reference":
                    comment = session.create_comment(
                        text=f"Custom genome reference: {row['text']}",
                        author_id=user.id,
                    )
                elif row["context"] == "assay_tech_selection":
                    comment = session.create_comment(
                        text=f"Additional info from assay selection: {row['text']}",
                        author_id=user.id,
                    )
                else:
                    raise ValueError(f"Unknown comment context: {row['context']}")
                    
                session.add_seq_request_comment(
                    seq_request_id=self.seq_request.id,
                    comment_id=comment.id
                )

        self.__update_data(
            sample_table=sample_table,
            library_table=library_table,
            visium_table=visium_table,
            cmo_table=cmo_table
        )

        flash(f"Added {library_table.shape[0]} libraries to sequencing request.", "success")
        logger.info(f"{self.uuid}: added libraries to sequencing request.")

        newdir = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_ANNOTATION.dir, str(self.seq_request.id))
        os.makedirs(newdir, exist_ok=True)
        shutil.copy(self.path, os.path.join(newdir, f"{self.uuid}.tsv"))
        os.remove(self.path)

        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))