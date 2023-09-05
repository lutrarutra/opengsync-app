from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField

from wtforms.validators import DataRequired


class DualIndexForm(FlaskForm):
    sample = IntegerField("Sample", validators=[DataRequired()])
    sample_search = StringField()

    adapter = StringField("Adapter", validators=[DataRequired()])
    adapter_search = StringField("Adapter")

    index_i7 = StringField("Index i7 Sequence")
    index_i7_id = IntegerField("Index i7", validators=[DataRequired()])
    
    index_i5 = StringField("Index i5 Sequence")
    index_i5_id = IntegerField("Index i5", validators=[DataRequired()])
