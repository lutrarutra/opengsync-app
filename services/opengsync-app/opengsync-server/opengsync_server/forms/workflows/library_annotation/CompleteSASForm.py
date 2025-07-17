import os
from typing import Optional

import pandas as pd

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import (
    GenomeRef, LibraryType, FeatureType, FileType, SampleStatus, PoolType, AttributeType,
    AssayType, SubmissionType, MUXType, IndexType
)

from .... import db, logger, tools
from ...MultiStepForm import MultiStepForm


class CompleteSASForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-complete.html"
    _workflow_name = "library_annotation"
    _step_name = "complete_sas"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=CompleteSASForm._workflow_name, step_name=CompleteSASForm._step_name,
            uuid=uuid, formdata=formdata, previous_form=previous_form, step_args={}
        )
        
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.library_table = self.tables["library_table"]
        self.sample_table = self.tables["sample_table"]
        self.sample_pooling_table = self.tables["sample_pooling_table"]
        self.barcode_table = self.tables.get("barcode_table")
        self.pool_table = self.tables.get("pool_table")
        self.feature_table = self.tables.get("feature_table")
        self.library_properties_table = self.tables.get("library_properties_table")
        self.flex_table = self.tables.get("flex_table")
        self.comment_table = self.tables.get("comment_table")
        self.mux_type = MUXType.get(self.metadata["mux_type_id"]) if self.metadata["mux_type_id"] is not None else None
        
        spatial_library_type_ids = [t.id for t in LibraryType.get_visium_library_types()] + [LibraryType.OPENST.id]
        self.contains_spatial_samples = self.library_table["library_type_id"].isin(spatial_library_type_ids).any()

        if self.contains_spatial_samples:
            if self.library_properties_table is None:
                logger.error(f"{self.uuid}: Library properties table not found for visium samples.")
                raise Exception("Library properties table not found for visium samples.")
            
            spatial_libraries = self.library_table[self.library_table["library_type_id"].isin(spatial_library_type_ids)]["library_name"].values
            self._context["spatial_table"] = self.library_properties_table[self.library_properties_table["library_name"] == spatial_libraries]
        else:
            self._context["spatial_table"] = None

        self._context["mux_type"] = self.mux_type

        if self.barcode_table is not None:
            self.barcode_table["pool"] = None
            for (library_name, pool_name), _ in self.library_table.groupby(["library_name", "pool"]):
                self.barcode_table.loc[self.barcode_table["library_name"] == library_name, "pool"] = pool_name
            self.barcode_table = tools.check_indices(self.barcode_table, groupby="pool")

        n_libraries = len(self.library_table)
        n_library_names = len(self.library_table["library_name"].unique())
        n_libraries_pooled = len(self.sample_pooling_table.duplicated(subset=["library_name", "mux_type_id"], keep=False))
        if n_libraries != n_library_names or n_libraries_pooled != n_libraries:
            logger.warning(self.sample_pooling_table[self.sample_pooling_table.duplicated(subset=["library_name", "mux_type_id"], keep=False)][["library_name", "mux_type_id", "sample_name"]])
            # logger.error(f"{self.uuid}: Library table contains duplicate library names or pooling entries.")
            # raise ValueError("Library table contains duplicate library names or pooling entries.")
        
        self.library_table["mux_type_id"] = None
        for (library_name, mux_type_id), _df in self.sample_pooling_table.groupby(["library_name", "mux_type_id"]):
            self.library_table.loc[self.library_table["library_name"] == library_name, "mux_type_id"] = mux_type_id
        
        if not formdata:
            self.__prepare()

    def __prepare(self):
        self._context["library_table"] = self.library_table
        self._context["sample_table"] = self.sample_table
        self._context["sample_pooling_table"] = self.sample_pooling_table
        self._context["barcode_table"] = self.barcode_table
        self._context["feature_table"] = self.feature_table
        self._context["library_properties_table"] = self.library_properties_table
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

        for sample_name, _df in self.sample_pooling_table.groupby("sample_name"):
            sample_node = {
                "node": node_idx,
                "name": sample_name,
            }
            nodes.append(sample_node)
            node_idx += 1

            links.append({
                "source": project_node["node"],
                "target": sample_node["node"],
                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["sample_name"] == sample_name]),
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

                    if input_type == "pooled":
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
                                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["library_name"] == row["library_name"]]),
                            })

                links.append({
                    "source": sample_node["node"],
                    "target": library_node["node"],
                    "value": LINK_WIDTH_UNIT,
                })

        self._context["nodes"] = nodes
        self._context["links"] = links
    
    def __update_data(self):
        self.update_table("sample_table", self.sample_table, False)
        self.update_table("library_table", self.library_table, False)
        if self.library_properties_table is not None:
            self.update_table("library_properties_table", self.library_properties_table, False)
        if self.sample_pooling_table is not None:
            self.update_table("sample_pooling_table", self.sample_pooling_table, False)

        self.update_data()

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.__prepare()
            return self.make_response()

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.get_project(project_id)) is None:
                logger.error(f"{self.uuid}: Project with id {project_id} not found.")
                raise ValueError(f"Project with id {project_id} not found.")
        else:
            project = db.create_project(
                name=self.metadata["project_name"],
                description=self.metadata["project_description"],
                owner_id=user.id,
                group_id=self.seq_request.group_id
            )

        predefined_attrs = [f"_attr_{attr.label}" for attr in AttributeType.as_list()]
        custom_sample_attributes = [attr for attr in self.sample_table.columns if attr.startswith("_attr_") and attr not in predefined_attrs]

        for idx, library_row in self.sample_table.iterrows():
            if pd.notna(library_row["sample_id"]):
                if (sample := db.get_sample(library_row["sample_id"])) is None:
                    logger.error(f"{self.uuid}: Sample with id {library_row['sample_id']} not found.")
                    raise ValueError(f"Sample with id {library_row['sample_id']} not found.")
            else:
                sample = db.create_sample(
                    name=library_row["sample_name"],
                    project_id=project.id,
                    owner_id=user.id,
                    status=None if self.seq_request.submission_type == SubmissionType.POOLED_LIBRARIES else SampleStatus.DRAFT
                )
                self.sample_table.at[idx, "sample_id"] = sample.id

            for attr in AttributeType.as_list():
                attr_label = f"_attr_{attr.label}"
                if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                    sample = db.set_sample_attribute(
                        sample_id=sample.id,
                        type=attr,
                        value=str(library_row[attr_label]),
                        name=None
                    )

            for attr_label in custom_sample_attributes:
                if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                    sample = db.set_sample_attribute(
                        sample_id=sample.id,
                        type=AttributeType.CUSTOM,
                        value=str(library_row[attr_label]),
                        name=attr_label.removeprefix("_attr_")
                    )

        self.sample_table["sample_id"] = self.sample_table["sample_id"].astype(int)

        if self.seq_request.submission_type == SubmissionType.POOLED_LIBRARIES:
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

        self.library_table["library_id"] = None
        for idx, library_row in self.library_table.iterrows():
            if self.library_properties_table is not None:
                visium_row = self.library_properties_table[self.library_properties_table["library_name"] == library_row["library_name"]].iloc[0]
                properties = dict([(k, v) for k, v in visium_row.to_dict().items() if pd.notna(v)])
                properties.pop("library_name", None)
                properties.pop("sample_name", None)
            else:
                properties = None

            if self.seq_request.submission_type == SubmissionType.POOLED_LIBRARIES:
                if self.pool_table is None:
                    logger.error(f"{self.uuid}: Pool table not found.")
                    raise ValueError("Pool table not found.")
                pool_id = int(self.pool_table[self.pool_table["pool_label"] == library_row["pool"]]["pool_id"].values[0])
            else:
                pool_id = None

            assay_type = AssayType.get(self.metadata["assay_type_id"])

            library = db.create_library(
                name=library_row["library_name"],
                sample_name=library_row["sample_name"],
                seq_request_id=self.seq_request.id,
                library_type=LibraryType.get(library_row["library_type_id"]),
                owner_id=user.id,
                genome_ref=GenomeRef.get(library_row["genome_id"]),
                pool_id=pool_id,
                assay_type=assay_type,
                properties=properties,
                mux_type=MUXType.get(library_row["mux_type_id"]) if pd.notna(library_row["mux_type_id"]) else None,
                nuclei_isolation=self.metadata.get("nuclei_isolation", False),
                seq_depth_requested=library_row["seq_depth"] if "seq_depth" in library_row and pd.notna(library_row["seq_depth"]) else None,
            )

            self.library_table.at[idx, "library_id"] = library.id
            
            if self.seq_request.submission_type == SubmissionType.POOLED_LIBRARIES:
                if self.barcode_table is None:
                    logger.error(f"{self.uuid}: Barcode table not found.")
                    raise ValueError("Barcode table not found.")

                library_barcodes = self.barcode_table[self.barcode_table["library_name"] == library_row["library_name"]]
                if library.type == LibraryType.TENX_SC_ATAC:
                    if len(library_barcodes) != 4:
                        logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(library_barcodes)}.")
                    index_type = IndexType.TENX_ATAC_INDEX
                else:
                    if library_barcodes["sequence_i5"].isna().all():
                        index_type = IndexType.SINGLE_INDEX
                    elif library_barcodes["sequence_i5"].isna().any():
                        logger.warning(f"{self.uuid}: Mixed index types found for library {library_row['library_name']}.")
                        index_type = IndexType.DUAL_INDEX
                    else:
                        index_type = IndexType.DUAL_INDEX

                library.index_type = index_type
                library = db.update_library(library)

                for _, barcode_row in library_barcodes.iterrows():
                    library = db.add_library_index(
                        library_id=library.id,
                        sequence_i7=barcode_row["sequence_i7"] if pd.notna(barcode_row["sequence_i7"]) else None,
                        sequence_i5=barcode_row["sequence_i5"] if pd.notna(barcode_row["sequence_i5"]) else None,
                        index_kit_i7_id=barcode_row["kit_i7_id"] if pd.notna(barcode_row["kit_i7_id"]) else None,
                        index_kit_i5_id=barcode_row["kit_i5_id"] if pd.notna(barcode_row["kit_i5_id"]) else None,
                        name_i7=barcode_row["name_i7"] if pd.notna(barcode_row["name_i7"]) else None,
                        name_i5=barcode_row["name_i5"] if pd.notna(barcode_row["name_i5"]) else None,
                    )

            for _, pooling_row in self.sample_pooling_table[self.sample_pooling_table["library_name"] == library_row["library_name"]].iterrows():
                if pooling_row["mux_type_id"] == MUXType.TENX_FLEX_PROBE.id:
                    if pd.isna(pooling_row["mux_barcode"]):
                        logger.error(f"{self.uuid}: Mux barcode is required for TENX_FLEX_PROBE mux type.")
                        raise ValueError("Mux barcode is required for TENX_FLEX_PROBE mux type.")
                    mux = {"barcode": pooling_row["mux_barcode"]}
                    mux_type = MUXType.TENX_FLEX_PROBE
                elif pooling_row["mux_type_id"] in [MUXType.TENX_OLIGO.id]:
                    if pd.isna(pooling_row["mux_barcode"]):
                        logger.error(f"{self.uuid}: Mux barcode is required for TENX_CMO mux type.")
                        raise ValueError("Mux barcode is required for TENX_CMO mux type.")
                    if pd.isna(pooling_row["mux_pattern"]):
                        logger.error(f"{self.uuid}: Mux pattern is required for TENX_CMO mux type.")
                        raise ValueError("Mux pattern is required for TENX_CMO mux type.")
                    if pd.isna(pooling_row["mux_read"]):
                        logger.error(f"{self.uuid}: Mux read is required for TENX_CMO mux type.")
                        raise ValueError("Mux read is required for TENX_CMO mux type.")
                    mux = {
                        "barcode": pooling_row["mux_barcode"],
                        "pattern": pooling_row["mux_pattern"],
                        "read": pooling_row["mux_read"]
                    }
                    mux_type = MUXType.get(pooling_row["mux_type_id"])
                elif pooling_row["mux_type_id"] == MUXType.TENX_ON_CHIP.id:
                    mux = {"barcode": pooling_row["mux_barcode"]}
                    mux_type = MUXType.TENX_ON_CHIP
                else:
                    mux = None
                    mux_type = None
                
                sample_ids = self.sample_table[self.sample_table["sample_name"] == pooling_row["sample_name"]]["sample_id"].values
                if len(sample_ids) != 1:
                    logger.error(f"{self.uuid}: Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                    raise ValueError(f"Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                db.link_sample_library(sample_id=sample_ids[0], library_id=library.id, mux=mux, mux_type=mux_type)

        self.library_table["library_id"] = self.library_table["library_id"].astype(int)

        if self.feature_table is not None:
            custom_features = self.feature_table[self.feature_table["feature_id"].isna()]
            for (feature, pattern, read, sequence), _df in custom_features.groupby(["feature", "pattern", "read", "sequence"]):
                feature = db.create_feature(
                    name=feature,
                    sequence=sequence,
                    pattern=pattern,
                    read=read,
                    type=FeatureType.ANTIBODY
                )
                feature_id = feature.id
                self.feature_table.loc[_df.index, "feature_id"] = feature_id

            for _, feature_row in self.feature_table.iterrows():
                libraries = self.library_table[self.library_table["library_name"] == feature_row["library_name"]]
                for _, library_row in libraries.iterrows():
                    db.link_feature_library(
                        feature_id=feature_row["feature_id"],
                        library_id=library_row["library_id"]
                    )

            self.feature_table["feature_id"] = self.feature_table["feature_id"].astype(int)
            
        if self.comment_table is not None:
            for _, comment_row in self.comment_table.iterrows():
                if comment_row["context"] == "visium_instructions":
                    db.create_comment(
                        text=f"Visium data instructions: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "custom_genome_reference":
                    db.create_comment(
                        text=f"Custom genome reference: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "assay_tech_selection":
                    db.create_comment(
                        text=f"Additional info from assay selection: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "i7_option":
                    db.create_comment(
                        text=comment_row['text'],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "i5_option":
                    db.create_comment(
                        text=comment_row['text'],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                else:
                    logger.warning(f"Unknown comment context: {comment_row['context']}")
                    db.create_comment(
                        text=comment_row["context"].replace("_", " ").capitalize() + ": " + comment_row["text"],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )

        self.__update_data()

        flash(f"Added {self.library_table.shape[0]} libraries to sequencing request.", "success")
        logger.info(f"{self.uuid}: added libraries to sequencing request.")

        newdir = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_ANNOTATION.dir, str(self.seq_request.id))
        os.makedirs(newdir, exist_ok=True)
        self.complete(os.path.join(newdir, f"{self.uuid}.msf"))

        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))