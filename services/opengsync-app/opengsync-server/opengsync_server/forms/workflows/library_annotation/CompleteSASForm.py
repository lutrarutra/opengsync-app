import os

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import (
    GenomeRef, LibraryType, FeatureType, MediaFileType, SampleStatus, PoolType, AttributeType,
    AssayType, SubmissionType, MUXType, IndexType, BarcodeOrientation
)

from .... import db, logger, tools
from ...MultiStepForm import MultiStepForm
from ....core.RunTime import runtime


class CompleteSASForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-complete.html"
    _workflow_name = "library_annotation"
    _step_name = "complete_sas"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=CompleteSASForm._workflow_name, step_name=CompleteSASForm._step_name,
            uuid=uuid, formdata=formdata, step_args={}
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
        self.comment_table = self.tables.get("comment_table")
        self.mux_type = MUXType.get(self.metadata["mux_type_id"]) if self.metadata["mux_type_id"] is not None else None

        self.abc_libraries = self.library_table[
            self.library_table["library_type_id"].isin(
                [LibraryType.TENX_ANTIBODY_CAPTURE.id, LibraryType.TENX_SC_ABC_FLEX.id]
            )
        ]["library_name"]

        if self.barcode_table is not None:
            self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
            self.barcode_table.loc[
                pd.notna(self.barcode_table["orientation_i7_id"]) &
                (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
                "orientation_id"
            ] = None
        
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
        self._context["comment_table"] = self.comment_table
        self._context["pool_table"] = self.pool_table

        input_type = "raw" if "pool" not in self.library_table.columns else "pooled"

        LINK_WIDTH_UNIT = 1
        nodes = []
        links = []

        project_node = {
            "node": 0,
            "name": self.metadata["project_title"],
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

    def process_request(self, user: models.User) -> Response:  # type: ignore
        if not self.validate():
            self.__prepare()
            return self.make_response()

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with id {project_id} not found.")
                raise ValueError(f"Project with id {project_id} not found.")
        else:
            project = db.projects.create(
                title=self.metadata["project_title"],
                description=self.metadata["project_description"],
                owner_id=user.id,
                group_id=self.seq_request.group_id
            )

        predefined_attrs = [f"_attr_{attr.label}" for attr in AttributeType.as_list()]
        custom_sample_attributes = [attr for attr in self.sample_table.columns if attr.startswith("_attr_") and attr not in predefined_attrs]

        for idx, library_row in self.sample_table.iterrows():
            if pd.notna(library_row["sample_id"]):
                if (sample := db.samples.get(library_row["sample_id"])) is None:
                    logger.error(f"{self.uuid}: Sample with id {library_row['sample_id']} not found.")
                    raise ValueError(f"Sample with id {library_row['sample_id']} not found.")
            else:
                sample = db.samples.create(
                    name=library_row["sample_name"],
                    project_id=project.id,
                    owner_id=user.id,
                    status=None if self.seq_request.submission_type == SubmissionType.POOLED_LIBRARIES else SampleStatus.DRAFT
                )
                self.sample_table.at[idx, "sample_id"] = sample.id

            for attr in AttributeType.as_list():
                attr_label = f"_attr_{attr.label}"
                if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                    sample = db.samples.set_attribute(
                        sample_id=sample.id,
                        type=attr,
                        value=str(library_row[attr_label]),
                        name=None
                    )

            for attr_label in custom_sample_attributes:
                if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                    sample = db.samples.set_attribute(
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
                    if (pool := db.pools.get(library_row["pool_id"])) is None:
                        logger.error(f"{self.uuid}: Pool with id {library_row['pool_id']} not found.")
                        raise ValueError(f"Pool with id {library_row['pool_id']} not found.")
                else:
                    pool = db.pools.create(
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

            library = db.libraries.create(
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
                        index_type = IndexType.SINGLE_INDEX_I7
                    elif library_barcodes["sequence_i5"].isna().any():
                        logger.warning(f"{self.uuid}: Mixed index types found for library {library_row['library_name']}.")
                        index_type = IndexType.DUAL_INDEX
                    else:
                        index_type = IndexType.DUAL_INDEX

                library.index_type = index_type
                db.libraries.update(library)

                for _, barcode_row in library_barcodes.iterrows():
                    if int(barcode_row["index_type_id"]) != index_type.id:
                        logger.error(f"{self.uuid}: Index type mismatch for library {library_row['library_name']}. Expected {index_type}, found {IndexType.get(barcode_row['index_type_id'])}.")
                        logger.warning(self.barcode_table)
                        logger.warning(self.library_table)

                    orientation = None
                    if pd.notna(barcode_row["orientation_i7_id"]):
                        orientation = BarcodeOrientation.get(int(barcode_row["orientation_i7_id"]))

                    if orientation is not None and pd.notna(barcode_row["orientation_i5_id"]):
                        if orientation.id != int(barcode_row["orientation_i5_id"]):
                            logger.error(f"{self.uuid}: Conflicting orientations for i7 and i5 in library {library_row['library_name']}.")
                            raise ValueError("Conflicting orientations for i7 and i5.")

                    library = db.libraries.add_index(
                        library_id=library.id,
                        sequence_i7=barcode_row["sequence_i7"] if pd.notna(barcode_row["sequence_i7"]) else None,
                        sequence_i5=barcode_row["sequence_i5"] if pd.notna(barcode_row["sequence_i5"]) else None,
                        index_kit_i7_id=barcode_row["kit_i7_id"] if pd.notna(barcode_row["kit_i7_id"]) else None,
                        index_kit_i5_id=barcode_row["kit_i5_id"] if pd.notna(barcode_row["kit_i5_id"]) else None,
                        name_i7=barcode_row["name_i7"] if pd.notna(barcode_row["name_i7"]) else None,
                        name_i5=barcode_row["name_i5"] if pd.notna(barcode_row["name_i5"]) else None,
                        orientation=orientation,
                    )

            for _, pooling_row in self.sample_pooling_table[self.sample_pooling_table["library_name"] == library_row["library_name"]].iterrows():
                if pooling_row["mux_type_id"] == MUXType.TENX_FLEX_PROBE.id:
                    if self.seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_barcode"]):
                        logger.error(f"{self.uuid}: Mux barcode is required for TENX_FLEX_PROBE mux type.")
                        raise ValueError("Mux barcode is required for TENX_FLEX_PROBE mux type.")
                    
                    mux = {"barcode": pooling_row["mux_barcode"]}
                elif pooling_row["mux_type_id"] in [MUXType.TENX_OLIGO.id]:
                    if self.seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_barcode"]):
                        logger.error(f"{self.uuid}: Mux barcode is required for TENX_OLIGO mux type.")
                        raise ValueError("Mux barcode is required for TENX_OLIGO mux type.")
                    if self.seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_pattern"]):
                        logger.error(f"{self.uuid}: Mux pattern is required for TENX_OLIGO mux type.")
                        raise ValueError("Mux pattern is required for TENX_OLIGO mux type.")
                    if self.seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_read"]):
                        logger.error(f"{self.uuid}: Mux read is required for TENX_OLIGO mux type.")
                        raise ValueError("Mux read is required for TENX_OLIGO mux type.")
                    
                    mux = {
                        "barcode": pooling_row["mux_barcode"],
                        "pattern": pooling_row["mux_pattern"],
                        "read": pooling_row["mux_read"]
                    }

                elif pooling_row["mux_type_id"] == MUXType.TENX_ON_CHIP.id:
                    mux = {"barcode": pooling_row["mux_barcode"]}
                elif pooling_row["mux_type_id"] == MUXType.TENX_ABC_HASH.id:
                    mux = {
                        "barcode": pooling_row["mux_barcode"],
                        "pattern": pooling_row["mux_pattern"],
                        "read": pooling_row["mux_read"]
                    }
                else:
                    mux = None
                
                sample_ids = self.sample_table[self.sample_table["sample_name"] == pooling_row["sample_name"]]["sample_id"].values
                if len(sample_ids) != 1:
                    logger.error(f"{self.uuid}: Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                    raise ValueError(f"Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                db.links.link_sample_library(sample_id=sample_ids[0], library_id=library.id, mux=mux)

        self.library_table["library_id"] = self.library_table["library_id"].astype(int)

        if self.feature_table is not None:
            custom_features = self.feature_table[self.feature_table["feature_id"].isna()]
            for (identifier, feature, pattern, read, sequence), _df in custom_features.groupby(["identifier", "feature", "pattern", "read", "sequence"], dropna=False):
                feature = db.features.create(
                    identifier=identifier if pd.notna(identifier) else None,
                    name=feature,
                    sequence=sequence,
                    pattern=pattern,
                    read=read,
                    type=FeatureType.ANTIBODY
                )
                self.feature_table.loc[_df.index, "feature_id"] = feature.id

            self.feature_table["feature_id"] = self.feature_table["feature_id"].astype(int)
            
            for _, library_row in self.library_table.iterrows():
                mask = (
                    (self.feature_table["library_name"] == library_row["library_name"]) |
                    self.feature_table["library_name"].isna()
                )
                if len(ids := self.feature_table[mask]["feature_id"].values.tolist()) > 0:
                    db.links.link_features_library(feature_ids=ids, library_id=int(library_row["library_id"]))
            
        if self.comment_table is not None:
            for _, comment_row in self.comment_table.iterrows():
                if comment_row["context"] == "visium_instructions":
                    db.comments.create(
                        text=f"Visium data instructions: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "custom_genome_reference":
                    db.comments.create(
                        text=f"Custom genome reference: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "assay_tech_selection":
                    db.comments.create(
                        text=f"Additional info from assay selection: {comment_row['text']}",
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "i7_option":
                    db.comments.create(
                        text=comment_row['text'],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                elif comment_row["context"] == "i5_option":
                    db.comments.create(
                        text=comment_row['text'],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )
                else:
                    logger.warning(f"Unknown comment context: {comment_row['context']}")
                    db.comments.create(
                        text=comment_row["context"].replace("_", " ").capitalize() + ": " + comment_row["text"],
                        author_id=user.id, seq_request_id=self.seq_request.id
                    )

        self.__update_data()

        flash(f"Added {self.library_table.shape[0]} libraries to sequencing request.", "success")
        logger.info(f"{self.uuid}: added libraries to sequencing request.")

        newdir = os.path.join(runtime.app.media_folder, MediaFileType.LIBRARY_ANNOTATION.dir, str(self.seq_request.id))
        os.makedirs(newdir, exist_ok=True)
        self.complete(os.path.join(newdir, f"{self.uuid}.msf"))

        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))