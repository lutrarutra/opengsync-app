from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FieldList, FormField

from wtforms.validators import DataRequired, Optional

from ..categories import LibraryType


class IndexSeqForm(FlaskForm):
    sequence = StringField(validators=[DataRequired()])
    index_seq_id = IntegerField(validators=[DataRequired()])


class IndexForm(FlaskForm):
    sample = IntegerField("Sample", validators=[DataRequired()])
    adapter = StringField("Adapter", validators=[Optional()])
    indices = FieldList(FormField(IndexSeqForm), min_entries=0)


def __crete_dual_index_form() -> IndexForm:
    form = IndexForm()
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index i7 Sequence"
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index i5 Sequence"
    return form


def __create_atac_index_form() -> IndexForm:
    form = IndexForm()
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index 1 Sequence"
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index 2 Sequence"
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index 3 Sequence"
    form.indices.append_entry()
    form.indices.entries[-1].sequence.label.text = "Index 4 Sequence"
    return form


def create_index_form(library_type: LibraryType) -> IndexForm:
    if library_type in [LibraryType.SC_RNA, LibraryType.SN_RNA]:
        return __crete_dual_index_form()
    elif library_type in [LibraryType.SC_ATAC]:
        return __create_atac_index_form()

    raise NotImplementedError(f"Index form for library type '{library_type}' not implemented.")
