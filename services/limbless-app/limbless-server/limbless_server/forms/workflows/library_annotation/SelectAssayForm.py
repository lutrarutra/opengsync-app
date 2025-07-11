from typing import Optional

from flask import Response
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, BooleanField, FormField, StringField
from wtforms.validators import Optional as OptionalValidator, Length, DataRequired

from limbless_db import models
from limbless_db.categories import AssayType, GenomeRef, MUXType

from .... import logger, db  # noqa
from ...MultiStepForm import MultiStepForm
from .DefineSamplesForm import DefineSamplesForm
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm


class OptionalAssaysForm(FlaskForm):
    vdj_b = BooleanField("VDJ-B", description="BCR-sequencing", default=False)
    vdj_t = BooleanField("VDJ-T", description="TCR-sequencing", default=False)
    vdj_t_gd = BooleanField("VDJ-T-GD", description="TCR-GD-sequencing", default=False)
    crispr_screening = BooleanField("CRISPR Screening", default=False)
    antibody_capture = BooleanField("Cell Surface Protein Capture", description="Antibody Capture", default=False)
    antibody_capture_kit = StringField(description="Antibody Capture Kit", validators=[OptionalValidator(), Length(max=64)])


class AdditionalSerevicesForm(FlaskForm):
    oligo_multiplexing = BooleanField("Sample Multiplexing using Oligo-based Cell Tagging for 10X Libraries", description="Multiple samples per library with oligo-based cell tagging, e.g. CMO/HTO/LMO..", default=False)
    oligo_multiplexing_kit = StringField(description="Multiplexing Kit", validators=[OptionalValidator(), Length(max=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH)])
    ocm_multiplexing = BooleanField("On-Chip Multiplexing for 10X GEM-X Libraries", description="Multiple samples per library using 10X On-Chip Multiplexing", default=False)
    nuclei_isolation = BooleanField("Nuclei Isolation", default=False)


class SelectAssayForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-select_assay.html"
    _workflow_name = "library_annotation"
    _step_name = "specify_assay"

    assay_type = SelectField("Assay Type", choices=AssayType.as_selectable(), validators=[DataRequired()], coerce=int)
    additional_info = TextAreaField("Additional Information", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)])
    optional_assays = FormField(OptionalAssaysForm)
    additional_services = FormField(AdditionalSerevicesForm)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.metadata["workflow_type"] == "tech"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=SelectAssayForm._workflow_name,
            step_name=SelectAssayForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.assay_type.data is None or AssayType.get(self.assay_type.data) == AssayType.CUSTOM:
            self.assay_type.errors = ("Please select an assay type.",)
        
        if self.optional_assays.antibody_capture.data and not self.optional_assays.antibody_capture_kit.data:
            self.optional_assays.antibody_capture_kit.errors = ("Please specify an antibody capture kit.",)
        
        if self.additional_services.oligo_multiplexing.data and not self.additional_services.oligo_multiplexing_kit.data:
            self.additional_services.oligo_multiplexing_kit.errors = ("Please specify a multiplexing kit.",)

        if self.errors:
            return False
        
        genome_map = {}
        for id, e in GenomeRef.as_tuples():
            genome_map[e.display_name] = id
        
        try:
            self.assay_type_enum = AssayType.get(int(self.assay_type.data))
        except ValueError:
            self.assay_type.errors = ("Invalid assay type",)
            return False

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        assay_type = AssayType.get(self.assay_type.data)
        oligo_multiplexing = self.additional_services.oligo_multiplexing.data
        ocm_multiplexing = self.additional_services.ocm_multiplexing.data
        flex_barcode_multiplexing = assay_type in [AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]
        
        self.metadata["assay_type_id"] = assay_type.id
        self.metadata["mux_type_id"] = None
        if oligo_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_OLIGO.id
        elif ocm_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_ON_CHIP.id
        elif flex_barcode_multiplexing:
            self.metadata["mux_type_id"] = MUXType.TENX_FLEX_PROBE.id
            
        self.metadata["nuclei_isolation"] = self.additional_services.nuclei_isolation.data
        self.metadata["antibody_capture"] = self.optional_assays.antibody_capture.data
        self.metadata["vdj_b"] = self.optional_assays.vdj_b.data
        self.metadata["vdj_t"] = self.optional_assays.vdj_t.data
        self.metadata["vdj_t_gd"] = self.optional_assays.vdj_t_gd.data
        self.metadata["crispr_screening"] = self.optional_assays.crispr_screening.data

        if self.additional_services.oligo_multiplexing_kit.data:
            self.add_comment(context="oligo_multiplexing_kit", text=self.additional_services.oligo_multiplexing_kit.data)

        if self.optional_assays.antibody_capture_kit.data:
            self.add_comment(context="antibody_capture_kit", text=self.optional_assays.antibody_capture_kit.data)

        if self.additional_info.data:
            self.add_comment(context="assay_tech_selection", text=self.additional_info.data)

        self.update_data()

        if DefineMultiplexedSamplesForm.is_applicable(self):
            next_form = DefineMultiplexedSamplesForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = DefineSamplesForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)

        return next_form.make_response()
        
        
