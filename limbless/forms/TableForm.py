from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import TextAreaField


class TableForm(FlaskForm):
    file = FileField("File", validators=[])
    data = TextAreaField("Sample Sheet (csv/tsv)", validators=[])
