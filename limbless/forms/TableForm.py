from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import TextAreaField


class TableForm(FlaskForm):
    file = FileField("File", validators=[FileAllowed(["csv", "tsv"])])
    data = TextAreaField("Sample Sheet (csv/tsv)", validators=[])
