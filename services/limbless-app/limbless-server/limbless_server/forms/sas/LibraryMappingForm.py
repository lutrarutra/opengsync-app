from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField
from wtforms.validators import DataRequired, Optional as OptionalValidator


from limbless_db.core.categories import LibraryType
from ... import tools
from ..TableDataForm import TableDataForm
from ..HTMXFlaskForm import HTMXFlaskForm

from .IndexKitMappingForm import IndexKitMappingForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .BarcodeCheckForm import BarcodeCheckForm
from .VisiumAnnotationForm import VisiumAnnotationForm


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
    _template_path = "components/popups/seq_request/sas-4.html"
    
    input_fields = FieldList(FormField(LibrarySubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()

        df = data["library_table"]
        
        library_types = df["library_type"].unique().tolist()
        library_types = [library_type if library_type and not pd.isna(library_type) else "Library" for library_type in library_types]

        for i, library_type in enumerate(library_types):
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
                    similars = tools.connect_similar_strings(LibraryType.as_selectable(), [library_type], similars=LibrarySubForm._similars, cutoff=0.2)
                    if (similar := similars[library_type]) is not None:
                        selected_library_type = LibraryType.get(similar)

            if selected_library_type is not None:
                self.input_fields[i].library_type.process_data(selected_library_type.value.id)

        data["library_table"] = df
        self.update_data(data)

        return {}

    def __parse(self) -> dict[str, pd.DataFrame]:
        data = self.get_data()
        df = data["library_table"]

        df.loc[df["library_type"].isna(), "library_type"] = "Library"
        library_types = df["library_type"].unique()
        library_types = [library_type if library_type and not pd.isna(library_type) else None for library_type in library_types]
        df["library_type_id"] = None
        for i, library_type in enumerate(library_types):
            df.loc[df["library_type"] == library_type, "library_type_id"] = int(self.input_fields[i].library_type.data)
        
        df["library_type"] = df["library_type_id"].apply(lambda x: LibraryType.get(x).value.description)

        df["is_cmo_sample"] = False
        for sample_name, _df in df.groupby("sample_name"):
            if LibraryType.MULTIPLEXING_CAPTURE.value.id in _df["library_type_id"].unique():
                df.loc[df["sample_name"] == sample_name, "is_cmo_sample"] = True

        data["library_table"] = df
        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response(**context)
        
        data = self.__parse()

        if "index_kit" in data["library_table"] and not data["library_table"]["index_kit"].isna().all():
            index_kit_mapping_form = IndexKitMappingForm(uuid=self.uuid)
            context = index_kit_mapping_form.prepare(data) | context
            return index_kit_mapping_form.make_response(**context)
        
        if data["library_table"]["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.value.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(uuid=self.uuid)
            context = cmo_reference_input_form.prepare(data) | context
            return cmo_reference_input_form.make_response(**context)
        
        if (data["library_table"]["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.value.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)
        
        if "pool" in data["library_table"].columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)

        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data) | context
        return barcode_check_form.make_response(**context)