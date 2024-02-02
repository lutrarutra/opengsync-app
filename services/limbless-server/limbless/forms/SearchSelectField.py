from wtforms import Field, widgets


class SearchSelectField(Field):
    search_bar_widget = widgets.SearchInput()
    data_widget = widgets.NumberInput()
    
    def __init__(self, label="Search", validators=None):
        super().__init__(label=label, validators=validators)

    