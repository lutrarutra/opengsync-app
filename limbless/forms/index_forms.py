from typing import Literal

from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FieldList, FormField
from wtforms.validators import DataRequired, Optional

from ..models import Library
from ..categories import LibraryType
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession
from .. import logger


class IndexSeqForm(FlaskForm):
    sequence = StringField(validators=[DataRequired()])
    index_seq_id = IntegerField(validators=[DataRequired()])


class IndexForm(FlaskForm):
    sample = IntegerField("Sample", validators=[DataRequired()])
    adapter = IntegerField("Adapter", validators=[Optional()])
    barcodes = FieldList(FormField(IndexSeqForm), min_entries=0)

    def custom_validate(
        self,
        library_id: int, user_id: int,
        db_handler: DBHandler,
        action: Literal["create", "update"] = "create",
    ) -> tuple[bool, "IndexForm"]:

        validated = self.validate()

        logger.debug(f"Validated: {validated}")

        if not validated:
            if "barcodes" in self.errors.keys():
                self.adapter.errors = ("Adapter is required",)
            return False, self

        with DBSession(db_handler) as session:
            if (library := session.get_library(library_id)) is None:
                logger.error(f"Library with id {library_id} does not exist.")
                return False, self
            
            library_samples = library.samples
            ids = [sample.id for sample in library_samples]
            if self.sample.data is None:
                self.sample.errors = ("Sample is required",)
                validated = False
            else:
                if action == "create":
                    if self.sample.data in ids:
                        self.sample.errors = ("Sample is already in this library",)
                        validated = False
                elif action == "update":
                    if self.sample.data not in ids:
                        self.sample.errors = ("Sample is not in this library",)
                        validated = False

            # TODO: check that barcode_id is not used in the library
            for sample in library_samples:
                logger.debug(sample.barcodes)

        return validated, self
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    

def __crete_dual_index_form() -> IndexForm:
    form = IndexForm()
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index i7 Sequence"
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index i5 Sequence"
    return form


def __create_atac_index_form() -> IndexForm:
    form = IndexForm()
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index 1 Sequence"
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index 2 Sequence"
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index 3 Sequence"
    form.barcodes.append_entry()
    form.barcodes.entries[-1].sequence.label.text = "Index 4 Sequence"
    return form


def create_index_form(library: Library) -> IndexForm:
    if library.is_raw_library():
        return IndexForm()
    if library.library_type in [LibraryType.DUAL_INDEX]:
        return __crete_dual_index_form()
    elif library.library_type in [LibraryType.SC_ATAC]:
        return __create_atac_index_form()

    raise NotImplementedError(f"Index form for library type '{library.library_type}' not implemented.")
