import pandas as pd

from flask import Response
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, BooleanField, FormField, StringField
from wtforms.validators import Optional as OptionalValidator, Length

from opengsync_db import models
from opengsync_db.categories import ServiceType, MUXType, LibraryTypeEnum, LibraryType, SubmissionType
from opengsync_server.forms.MultiStepForm import StepFile

from .... import logger, db  # noqa
from ...MultiStepForm import MultiStepForm
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .CustomAssayAnnotationForm import CustomAssayAnnotationFrom
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm


class OptionalAssaysForm(FlaskForm):
    vdj_b = BooleanField("VDJ-B", description="BCR-sequencing", default=False)
    vdj_t = BooleanField("VDJ-T", description="TCR-sequencing", default=False)
    vdj_t_gd = BooleanField("VDJ-T-GD", description="TCR-GD-sequencing", default=False)
    crispr_screening = BooleanField("CRISPR Screening", default=False)
    antibody_capture = BooleanField("Cell Surface Protein Capture", description="Antibody Capture", default=False)
    antibody_multiplexing = BooleanField("+ Sample Multiplexing with Antibody-based Cell Hashing", description="Multiple samples per library with antibody-based cell tagging. Only available with cell surface protein capture.", default=False)
    antibody_capture_kit = StringField(description="Antibody Capture Kit", validators=[OptionalValidator(), Length(max=64)])
    
    parse_mux = BooleanField("Multiple Samples per Sub-Library", description="Multiple samples per sub-library with Parse Biosciences multiplexing technology.", default=False)
    parse_tcr = BooleanField(LibraryType.PARSE_EVERCODE_TCR.name, default=False)
    parse_bcr = BooleanField(LibraryType.PARSE_EVERCODE_BCR.name, default=False)
    parse_crispr = BooleanField(LibraryType.PARSE_SC_CRISPR.name, default=False)
    
    Parse_kits = [(1, "WT_mini"), (2, "WT"), (3, "WT_mega"), (4, "WT_mega_384"), (5, "WT_penta"), (6, "WT_penta_384")]
    parse_kit = SelectField(validators=[OptionalValidator()], choices=[(-1, "")] + Parse_kits, coerce=int, default=-1)

    Parse_chemistries = [(1, "v1"), (2, "v2"), (3, "v3")]
    parse_chemistry = SelectField(validators=[OptionalValidator()], choices=[(-1, "")] + Parse_chemistries, coerce=int, default=-1)


class AdditionalSerevicesForm(FlaskForm):
    oligo_multiplexing = BooleanField("Sample Multiplexing using Oligo-based Cell Tagging for 10X Libraries", description="Multiple samples per library with oligo-based cell tagging, e.g. CMO/HTO/LMO..", default=False)
    oligo_multiplexing_kit = StringField(description="Multiplexing Kit", validators=[OptionalValidator(), Length(max=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH)])
    ocm_multiplexing = BooleanField("On-Chip Multiplexing for 10X GEM-X Libraries", description="Multiple samples per library using 10X On-Chip Multiplexing", default=False)
    nuclei_isolation = BooleanField("Nuclei Isolation", default=False)


class SelectServiceForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-select_service.html"
    _workflow_name = "library_annotation"
    _step_name = "select_service"

    service_type = SelectField("Service Type", choices=[(-1, "Select Service")] + ServiceType.as_selectable(), validators=[OptionalValidator()], coerce=int, default=-1)
    additional_info = TextAreaField("Additional Information", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)])
    optional_assays = FormField(OptionalAssaysForm)
    additional_services = FormField(AdditionalSerevicesForm)

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=SelectServiceForm._workflow_name,
            step_name=SelectServiceForm._step_name,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.sample_table = self.tables["sample_table"]

    def fill_previous_form(self, previous_form: StepFile):
        self.service_type.data = previous_form.metadata.get("service_type_id")
        self.additional_services.nuclei_isolation.data = previous_form.metadata.get("nuclei_isolation", False)
        self.optional_assays.antibody_capture.data = previous_form.metadata.get("antibody_capture", False)
        self.optional_assays.vdj_b.data = previous_form.metadata.get("vdj_b", False)
        self.optional_assays.vdj_t.data = previous_form.metadata.get("vdj_t", False)
        self.optional_assays.vdj_t_gd.data = previous_form.metadata.get("vdj_t_gd", False)
        self.optional_assays.crispr_screening.data = previous_form.metadata.get("crispr_screening", False)
        self.optional_assays.antibody_multiplexing.data = previous_form.metadata.get("antibody_multiplexing", False)

        self.optional_assays.parse_kit.data = previous_form.metadata.get("parse_kit", -1)
        self.optional_assays.parse_chemistry.data = previous_form.metadata.get("parse_chemistry", -1)
        self.optional_assays.parse_crispr.data = previous_form.metadata.get("parse_crispr", False)
        self.optional_assays.parse_mux.data = previous_form.metadata["mux_type_id"] == MUXType.PARSE_WELLS.id
        self.optional_assays.parse_tcr.data = previous_form.metadata.get("parse_tcr", False)
        self.optional_assays.parse_bcr.data = previous_form.metadata.get("parse_bcr", False)

        self.optional_assays.antibody_capture_kit.data = previous_form.metadata.get("antibody_capture_kit", "")
        
        if previous_form.metadata.get("mux_type_id") == MUXType.TENX_OLIGO.id:
            self.additional_services.oligo_multiplexing.data = True
            self.additional_services.oligo_multiplexing_kit.data = previous_form.metadata.get("oligo_multiplexing_kit", "")
        elif previous_form.metadata.get("mux_type_id") == MUXType.TENX_ON_CHIP.id:
            self.additional_services.ocm_multiplexing.data = True

        self.additional_info.data = previous_form.metadata.get("additional_info", "")

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.service_type.data is None:
            self.service_type.errors = ("Please select an assay type.",)
        
        try:
            self.service_type_enum = ServiceType.get(int(self.service_type.data))
        except ValueError:
            self.service_type.errors = ("Invalid assay type",)
            return False
        
        if self.service_type_enum == ServiceType.PARSE:
            if self.optional_assays.parse_kit.data == -1:
                self.optional_assays.parse_kit.errors = ("Please select a Parse kit.",)
            if self.optional_assays.parse_chemistry.data == -1:
                self.optional_assays.parse_chemistry.errors = ("Please select a Parse chemistry.",)
        
        if self.optional_assays.antibody_capture.data and not self.optional_assays.antibody_capture_kit.data:
            self.optional_assays.antibody_capture_kit.errors = ("Please specify an antibody capture kit.",)
        
        if self.additional_services.oligo_multiplexing.data and not self.additional_services.oligo_multiplexing_kit.data:
            self.additional_services.oligo_multiplexing_kit.errors = ("Please specify a multiplexing kit.",)

        if self.optional_assays.antibody_multiplexing.data and not self.optional_assays.antibody_capture.data:
            self.optional_assays.antibody_multiplexing.errors = ("Antibody-based cell hashing multiplexing requires cell surface protein capture.",)

        if self.optional_assays.antibody_multiplexing.data and self.additional_services.oligo_multiplexing.data:
            self.optional_assays.antibody_multiplexing.errors = ("Please select only one multiplexing method.",)
            self.additional_services.oligo_multiplexing_kit.errors = ("Please select only one multiplexing method.",)

        if self.optional_assays.antibody_multiplexing.data and self.additional_services.ocm_multiplexing.data:
            self.optional_assays.antibody_multiplexing.errors = ("Please select only one multiplexing method.",)
            self.additional_services.ocm_multiplexing.errors = ("Please select only one multiplexing method.",)

        if self.additional_services.oligo_multiplexing.data and self.additional_services.ocm_multiplexing.data:
            self.additional_services.oligo_multiplexing_kit.errors = ("Please select only one multiplexing method.",)
            self.additional_services.ocm_multiplexing.errors = ("Please select only one multiplexing method.",)

        if self.optional_assays.parse_mux.data and self.service_type_enum != ServiceType.PARSE:
            self.optional_assays.parse_mux.errors = ("Parse Biosciences multiplexing is only available with Parse Biosciences assays.",)

        if self.optional_assays.parse_mux.data and (self.additional_services.oligo_multiplexing.data or self.additional_services.ocm_multiplexing.data or self.optional_assays.antibody_multiplexing.data):
            self.optional_assays.parse_mux.errors = ("Please select only one multiplexing method.",)

        if self.optional_assays.antibody_multiplexing.data and self.service_type_enum in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
            self.optional_assays.antibody_multiplexing.errors = ("Antibody-based cell hashing multiplexing is not available with 10X Flex assays.",)

        if self.errors:
            return False

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        oligo_multiplexing = self.additional_services.oligo_multiplexing.data
        ocm_multiplexing = self.additional_services.ocm_multiplexing.data
        antibody_multiplexing = self.optional_assays.antibody_multiplexing.data
        flex_barcode_multiplexing = self.service_type_enum in [ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]
        parse_multiplexing = self.optional_assays.parse_mux.data
        
        self.metadata["service_type_id"] = self.service_type_enum.id
        self.metadata["mux_type_id"] = None
        self.metadata["oligo_multiplexing_kit"] = self.additional_services.oligo_multiplexing_kit.data
        self.metadata["antibody_capture_kit"] = self.optional_assays.antibody_capture_kit.data
        self.metadata["antibody_multiplexing"] = self.optional_assays.antibody_multiplexing.data

        if oligo_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_OLIGO.id
        elif ocm_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_ON_CHIP.id
        elif flex_barcode_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_FLEX_PROBE.id
        elif antibody_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_ABC_HASH.id
        elif parse_multiplexing:
            self.metadata["mux_type_id"] = MUXType.PARSE_WELLS.id
            
        self.metadata["nuclei_isolation"] = self.additional_services.nuclei_isolation.data
        self.metadata["antibody_capture"] = self.optional_assays.antibody_capture.data

        self.metadata["vdj_b"] = self.optional_assays.vdj_b.data
        self.metadata["vdj_t"] = self.optional_assays.vdj_t.data
        self.metadata["vdj_t_gd"] = self.optional_assays.vdj_t_gd.data
        self.metadata["crispr_screening"] = self.optional_assays.crispr_screening.data
        self.metadata["additional_info"] = self.additional_info.data

        self.metadata["parse_kit"] = self.optional_assays.parse_kit.data
        self.metadata["parse_chemistry"] = self.optional_assays.parse_chemistry.data
        self.metadata["parse_crispr"] = self.optional_assays.parse_crispr.data
        self.metadata["parse_tcr"] = self.optional_assays.parse_tcr.data
        self.metadata["parse_bcr"] = self.optional_assays.parse_bcr.data

        if self.additional_services.oligo_multiplexing_kit.data:
            self.add_comment(context="oligo_multiplexing_kit", text=self.additional_services.oligo_multiplexing_kit.data)

        if self.optional_assays.antibody_capture_kit.data:
            self.add_comment(context="antibody_capture_kit", text=self.optional_assays.antibody_capture_kit.data)

        if self.additional_info.data:
            self.add_comment(context="assay_tech_selection", text=self.additional_info.data)
        
        if (parse_chemistry := dict(OptionalAssaysForm.Parse_chemistries).get(self.optional_assays.parse_chemistry.data)) is not None:
            self.add_comment(context="parse_chemistry", text=parse_chemistry)

        if (parse_kit := dict(OptionalAssaysForm.Parse_kits).get(self.optional_assays.parse_kit.data)) is not None:
            self.add_comment(context="parse_kit", text=parse_kit)

        self.update_data()

        if DefineMultiplexedSamplesForm.is_applicable(self):
            next_form = DefineMultiplexedSamplesForm(seq_request=self.seq_request, uuid=self.uuid)
            return next_form.make_response()
        if self.service_type_enum == ServiceType.CUSTOM:
            sample_pooling_table = {
                "sample_pool": [],
                "sample_name": [],
            }
            for (sample_name,), _ in self.sample_table.groupby(["sample_name"], sort=False):
                sample_pooling_table["sample_pool"].append(sample_name)
                sample_pooling_table["sample_name"].append(sample_name)
                
            sample_pooling_table = pd.DataFrame(sample_pooling_table)
            self.add_table("sample_pooling_table", sample_pooling_table)
            self.update_data()
            next_form = CustomAssayAnnotationFrom(seq_request=self.seq_request, uuid=self.uuid)
            return next_form.make_response()
        
        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "library_type": [],
            "library_type_id": [],
        }

        sample_pooling_table = {
            "sample_name": [],
            "library_name": [],
            "sample_pool": [],
        }

        def add_library(sample_name: str, library_type: LibraryTypeEnum):
            library_name = f"{sample_name}_{library_type.identifier}"

            sample_pooling_table["sample_name"].append(sample_name)
            sample_pooling_table["library_name"].append(library_name)
            sample_pooling_table["sample_pool"].append(sample_name)

            library_table_data["library_name"].append(library_name)
            library_table_data["sample_name"].append(sample_name)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        for _, row in self.sample_table.iterrows():
            sample_name = row["sample_name"]

            for library_type in self.service_type_enum.library_types:
                add_library(sample_name, library_type)

            if self.optional_assays.antibody_capture.data:
                if self.service_type_enum in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
                    add_library(sample_name, LibraryType.TENX_SC_ABC_FLEX)
                else:
                    add_library(sample_name, LibraryType.TENX_ANTIBODY_CAPTURE)

            if self.optional_assays.vdj_b.data:
                add_library(sample_name, LibraryType.TENX_VDJ_B)

            if self.optional_assays.vdj_t.data:
                add_library(sample_name, LibraryType.TENX_VDJ_T)

            if self.optional_assays.vdj_t_gd.data:
                add_library(sample_name, LibraryType.TENX_VDJ_T_GD)

            if self.optional_assays.crispr_screening.data:
                add_library(sample_name, LibraryType.TENX_CRISPR_SCREENING)

            if self.optional_assays.parse_crispr.data:
                add_library(sample_name, LibraryType.PARSE_SC_CRISPR)
            
            if self.optional_assays.parse_tcr.data:
                add_library(sample_name, LibraryType.PARSE_EVERCODE_TCR)

            if self.optional_assays.parse_bcr.data:
                add_library(sample_name, LibraryType.PARSE_EVERCODE_BCR)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None

        sample_pooling_table = pd.DataFrame(sample_pooling_table)
        sample_pooling_table["mux_type_id"] = None

        self.add_table("library_table", library_table)
        self.add_table("sample_pooling_table", sample_pooling_table)
        self.update_data()

        if self.metadata["submission_type_id"] == SubmissionType.POOLED_LIBRARIES.id:
            next_form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()

        
        
