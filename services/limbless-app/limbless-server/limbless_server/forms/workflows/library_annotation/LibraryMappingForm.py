from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import tools, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm

from .IndexKitMappingForm import IndexKitMappingForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FRPAnnotationForm import FRPAnnotationForm
from .KitMappingForm import KitMappingForm
from .CompleteSASForm import CompleteSASForm


class LibrarySubForm(FlaskForm):
    _similars = {
        "custom": 0,
        "scrnaseq": 1,
        "scrna": 1,
        "geneexpression": 1,
        "gene expression": 1,
        "gex": 1,
        "snrnaseq": 2,
        "snrna": 2,
        "multiplexing capture": 3,
        "cmo": 3,
        "hto": 3,
        "atac": 4,
        "scatacseq": 4,
        "scatac": 4,
        "snatacseq": 5,
        "snatac": 5,
        "spatial transcriptomic": 6,
        "spatial transcriptomics": 6,
        "10xvisium": 6,
        "visium10x": 6,
        "visium": 6,
        "spatial": 6,
        "bcr": 7,
        "vdjb": 7,
        "vdjt": 8,
        "tcr": 8,
        "tcrt": 8,
        "tcrgd": 9,
        "tcrtgd": 9,
        "vdjtgd": 9,
        "antibodycapture": 10,
        "abc": 10,
        "crispr": 11,
        "bulkrnaseq": 100,
        "bulk": 100,
        "rnaseq": 100,
        "exomeseq": 101,
        "exome": 101,
        "es": 101,
        "wes": 101,
        "wholeexomeseq": 101,
        "wholeexome": 101,
        "wholeexomesequencing": 101,
        "genomeseq": 102,
        "genome": 102,
        "gs": 102,
        "wgs": 102,
        "wholegenomeseq": 102,
        "wholegenome": 102,
        "wholegenomesequencing": 102,
        "ampliconseq": 103,
        "amplicon": 103,
        "as": 103,
        "ampliconsequencing": 103,
        "rbsseq": 104,
        "rbs": 104,
        "cite": 105,
        "citeseq": 105,
        "atacseq": 106,
    }

    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    library_type = SelectField("Library Type", choices=LibraryType.as_selectable(), validators=[DataRequired()], default=None)


class LibraryMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-4.html"
    
    input_fields = FieldList(FormField(LibrarySubForm), min_entries=1)

    def __init__(self, seq_request: models.SeqRequest, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def prepare(self):
        library_table = self.tables["library_table"]

        for i, library_type in enumerate(library_table["library_type"].unique().tolist()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.raw_label.data = library_type
            
            selected_library_type = None
            if (selected_id := entry.library_type.data) is not None:
                try:
                    selected_id = int(selected_id)
                    selected_library_type = LibraryType.get(selected_id)
                except ValueError:
                    selected_id = None

            else:
                if library_type is not None:
                    similars = tools.connect_similar_strings(LibraryType.as_selectable(), [library_type], similars=LibrarySubForm._similars, cutoff=0.2)  # type: ignore
                    if (similar := similars[library_type]) is not None:
                        selected_library_type = LibraryType.get(similar)

            if selected_library_type is not None:
                self.input_fields[i].library_type.process_data(selected_library_type.id)
    
    def process_request(self) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response()
        
        library_table = self.tables["library_table"]

        library_table.loc[library_table["library_type"].isna(), "library_type"] = "Library"
        library_types = library_table["library_type"].unique()
        library_types = [library_type if library_type and not pd.isna(library_type) else None for library_type in library_types]
        library_table["library_type_id"] = None
        for i, library_type in enumerate(library_types):
            library_table.loc[library_table["library_type"] == library_type, "library_type_id"] = int(self.input_fields[i].library_type.data)
        
        library_table["library_type"] = library_table["library_type_id"].apply(lambda x: LibraryType.get(x).abbreviation)
        
        self.update_table("library_table", library_table)

        if "index_kit" in library_table and not library_table["index_kit"].isna().all():
            index_kit_mapping_form = IndexKitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            index_kit_mapping_form.prepare()
            return index_kit_mapping_form.make_response()
        
        if library_table["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (library_table["library_type_id"] == LibraryType.ANTIBODY_CAPTURE.id).any():
            kit_reference_input_form = KitMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return kit_reference_input_form.make_response()
        
        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if LibraryType.TENX_FLEX.id in library_table["library_type_id"].values and "pool" in library_table.columns:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()
        
        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response()

        complete_sas_form = CompleteSASForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response()