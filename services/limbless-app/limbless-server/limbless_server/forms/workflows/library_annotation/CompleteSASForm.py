import os
import shutil
from typing import Optional

import pandas as pd

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response

from limbless_db import models, DBSession
from limbless_db.categories import GenomeRef, LibraryType, FeatureType, FileType, SampleStatus, PoolType, AttributeType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm


class CompleteSASForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-complete.html"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[TableDataForm] = None, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.library_table = self.tables["library_table"]
        self.sample_table = self.tables["sample_table"]
        self.pooling_table = self.tables["pooling_table"]
        self.barcode_table = self.tables.get("barcode_table")
        self.pool_table = self.tables.get("pool_table")
        self.feature_table = self.tables.get("feature_table")
        self.cmo_table = self.tables.get("cmo_table")
        self.visium_table = self.tables.get("visium_table")
        self.flex_table = self.tables.get("flex_table")
        self.comment_table = self.tables.get("comment_table")

    def prepare(self):
        self._context["library_table"] = self.library_table
        self._context["sample_table"] = self.sample_table
        self._context["pooling_table"] = self.pooling_table
        self._context["barcode_table"] = self.barcode_table
        self._context["feature_table"] = self.feature_table
        self._context["cmo_table"] = self.cmo_table
        self._context["visium_table"] = self.visium_table
        self._context["flex_table"] = self.flex_table
        self._context["comment_table"] = self.comment_table
        self._context["pool_table"] = self.pool_table

        input_type = "raw" if "pool" not in self.library_table.columns else "pooled"

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

        library_nodes = {}

        for sample_name, _df in self.pooling_table.groupby("sample_name"):
            sample_node = {
                "node": node_idx,
                "name": sample_name,
            }
            nodes.append(sample_node)
            node_idx += 1

            links.append({
                "source": project_node["node"],
                "target": sample_node["node"],
                "value": LINK_WIDTH_UNIT * len(self.pooling_table[self.pooling_table["sample_name"] == sample_name]),
            })

            for _, row in _df.iterrows():
                if row["library_name"] in library_nodes.keys():
                    library_node = library_nodes[row["library_name"]]
                else:
                    library_node = {
                        "node": node_idx,
                        "name": row['library_name'],
                    }
                    library_nodes[row["library_name"]] = library_node
                    nodes.append(library_node)
                    node_idx += 1
                links.append({
                    "source": sample_node["node"],
                    "target": library_node["node"],
                    "value": LINK_WIDTH_UNIT,
                })

                if input_type == "raw":
                    continue
                
                for _, library_row in self.library_table[self.library_table["library_name"] == row["library_name"]].iterrows():
                    if (pool_node := pool_nodes.get(library_row["pool"])) is None:
                        pool_node = {
                            "node": node_idx,
                            "name": library_row["pool"],
                        }
                        nodes.append(pool_node)
                        node_idx += 1
                        pool_nodes[library_row["pool"]] = pool_node

                    links.append({
                        "source": library_node["node"],
                        "target": pool_node["node"],
                        "value": LINK_WIDTH_UNIT * len(_df),
                    })

        self._context["nodes"] = nodes
        self._context["links"] = links
    
    def __update_data(self):
        self.update_table("sample_table", self.sample_table, False)
        self.update_table("library_table", self.library_table, False)
        if self.visium_table is not None:
            self.update_table("visium_table", self.visium_table, False)
        if self.cmo_table is not None:
            self.update_table("cmo_table", self.cmo_table, False)

        self.update_data()

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response()

        if self.visium_table is not None:
            self.visium_table["id"] = None
            with DBSession(db) as session:
                for idx, visium_row in self.visium_table.iterrows():
                    visium_annotation = db.create_visium_annotation(
                        area=visium_row["area"],
                        image=visium_row["image"],
                        slide=visium_row["slide"],
                    )
                    self.visium_table.at[idx, "id"] = visium_annotation.id

            self.visium_table["id"] = self.visium_table["id"].astype(int)

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
            custom_sample_attributes = [attr for attr in self.sample_table.columns if attr.startswith("_attr_") and attr not in predefined_attrs]

            for idx, library_row in self.sample_table.iterrows():
                if pd.notna(library_row["sample_id"]):
                    if (sample := session.get_sample(library_row["sample_id"])) is None:
                        logger.error(f"{self.uuid}: Sample with id {library_row['sample_id']} not found.")
                        raise ValueError(f"Sample with id {library_row['sample_id']} not found.")
                else:
                    sample = session.create_sample(
                        name=library_row["sample_name"],
                        project_id=project.id,
                        owner_id=user.id,
                        status=SampleStatus.DRAFT
                    )
                    self.sample_table.at[idx, "sample_id"] = sample.id

                for attr in AttributeType.as_list():
                    attr_label = f"_attr_{attr.label}"
                    if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                        sample = session.set_sample_attribute(
                            sample_id=sample.id,
                            type=attr,
                            value=str(library_row[attr_label]),
                            name=None
                        )

                for attr_label in custom_sample_attributes:
                    if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                        sample = session.set_sample_attribute(
                            sample_id=sample.id,
                            type=AttributeType.CUSTOM,
                            value=str(library_row[attr_label]),
                            name=attr_label.removeprefix("_attr_")
                        )

        self.sample_table["sample_id"] = self.sample_table["sample_id"].astype(int)

        if self.metadata["workflow_type"] == "pooled":
            if self.pool_table is None:
                logger.error(f"{self.uuid}: Pool table not found.")
                raise ValueError("Pool table not found.")
            
            for idx, library_row in self.pool_table.iterrows():
                if pd.notna(library_row["pool_id"]):
                    if (pool := db.get_pool(library_row["pool_id"])) is None:
                        logger.error(f"{self.uuid}: Pool with id {library_row['pool_id']} not found.")
                        raise ValueError(f"Pool with id {library_row['pool_id']} not found.")
                else:
                    pool = db.create_pool(
                        name=library_row["pool_name"],
                        owner_id=user.id,
                        seq_request_id=self.seq_request.id,
                        pool_type=PoolType.EXTERNAL,
                        contact_name=self.metadata["pool_contact_name"],
                        contact_email=self.metadata["pool_contact_email"],
                        contact_phone=self.metadata["pool_contact_phone"],
                        num_m_reads_requested=library_row["num_m_reads_requested"]
                    )

                self.pool_table.at[idx, "pool_id"] = pool.id
                
            self.pool_table["pool_id"] = self.pool_table["pool_id"].astype(int)

        with DBSession(db) as session:
            self.library_table["library_id"] = None
            for idx, library_row in self.library_table.iterrows():
                if self.visium_table is not None:
                    visium_row = self.visium_table[self.visium_table["library_name"] == library_row["library_name"]].iloc[0]
                    visium_annotation_id = int(visium_row["id"])
                else:
                    visium_annotation_id = None

                if self.metadata["workflow_type"] == "pooled":
                    if self.pool_table is None:
                        logger.error(f"{self.uuid}: Pool table not found.")
                        raise ValueError("Pool table not found.")
                    pool_id = int(self.pool_table[self.pool_table["pool_label"] == library_row["pool"]]["pool_id"].values[0])
                else:
                    pool_id = None

                library = session.create_library(
                    name=library_row["library_name"],
                    sample_name=library_row["sample_name"],
                    seq_request_id=self.seq_request.id,
                    library_type=LibraryType.get(library_row["library_type_id"]),
                    owner_id=user.id,
                    genome_ref=GenomeRef.get(library_row["genome_id"]),
                    visium_annotation_id=visium_annotation_id,
                    pool_id=pool_id,
                    seq_depth_requested=library_row["seq_depth"] if "seq_depth" in library_row and pd.notna(library_row["seq_depth"]) else None,
                )

                self.library_table.at[idx, "library_id"] = library.id
                
                if self.metadata["workflow_type"] == "pooled":
                    for _, barcode_row in self.barcode_table[self.barcode_table["library_name"] == library_row["library_name"]].iterrows():
                        library = session.add_library_index(
                            library_id=library.id,
                            sequence_i7=barcode_row["sequence_i7"] if pd.notna(barcode_row["sequence_i7"]) else None,
                            sequence_i5=barcode_row["sequence_i5"] if pd.notna(barcode_row["sequence_i5"]) else None,
                            index_kit_i7_id=barcode_row["kit_i7_id"] if pd.notna(barcode_row["kit_i7_id"]) else None,
                            index_kit_i5_id=barcode_row["kit_i5_id"] if pd.notna(barcode_row["kit_i5_id"]) else None,
                            name_i7=barcode_row["name_i7"] if pd.notna(barcode_row["name_i7"]) else None,
                            name_i5=barcode_row["name_i5"] if pd.notna(barcode_row["name_i5"]) else None,
                        )

                library_samples = self.pooling_table[self.pooling_table["library_name"] == library_row["library_name"]]["sample_name"].values
                for _, sample_row in self.sample_table[self.sample_table["sample_name"].isin(library_samples)].iterrows():
                    session.link_sample_library(
                        sample_id=sample_row["sample_id"],
                        library_id=library.id,
                        cmo_sequence=sample_row["cmo_sequence"] if pd.notna(sample_row["cmo_sequence"]) else None,
                        cmo_pattern=sample_row["cmo_pattern"] if pd.notna(sample_row["cmo_pattern"]) else None,
                        cmo_read=sample_row["cmo_read"] if pd.notna(sample_row["cmo_read"]) else None,
                        flex_barcode=sample_row["flex_barcode"] if pd.notna(sample_row["flex_barcode"]) else None,
                    )

            self.library_table["library_id"] = self.library_table["library_id"].astype(int)

        if self.feature_table is not None:
            custom_features = self.feature_table[self.feature_table["feature_id"].isna()]
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
                    self.feature_table.loc[_df.index, "feature_id"] = feature_id

            with DBSession(db) as session:
                for _, feature_row in self.feature_table.iterrows():
                    libraries = self.library_table[self.library_table["library_name"] == feature_row["library_name"]]
                    for _, library_row in libraries.iterrows():
                        session.link_feature_library(
                            feature_id=feature_row["feature_id"],
                            library_id=library_row["library_id"]
                        )

            self.feature_table["feature_id"] = self.feature_table["feature_id"].astype(int)
            
        if self.comment_table is not None:
            for _, library_row in self.comment_table.iterrows():
                if library_row["context"] == "visium_instructions":
                    _ = session.create_comment(
                        text=f"Visium data instructions: {library_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif library_row["context"] == "custom_genome_reference":
                    _ = session.create_comment(
                        text=f"Custom genome reference: {library_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif library_row["context"] == "assay_tech_selection":
                    _ = session.create_comment(
                        text=f"Additional info from assay selection: {library_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                else:
                    raise ValueError(f"Unknown comment context: {library_row['context']}")

        self.__update_data()

        flash(f"Added {self.library_table.shape[0]} libraries to sequencing request.", "success")
        logger.info(f"{self.uuid}: added libraries to sequencing request.")

        newdir = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_ANNOTATION.dir, str(self.seq_request.id))
        os.makedirs(newdir, exist_ok=True)
        shutil.copy(self.path, os.path.join(newdir, f"{self.uuid}.tsv"))
        os.remove(self.path)

        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))