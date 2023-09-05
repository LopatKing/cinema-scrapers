from datetime import date

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Div, HTML, Fieldset, Button
from django.forms import ModelForm, ModelMultipleChoiceField, CheckboxSelectMultiple, DateField, SelectDateWidget

from cinemas.models import CinemaProvider


class StartScraperForm(ModelForm):
    cinema = ModelMultipleChoiceField(
        queryset=CinemaProvider.objects.filter(is_available=True),
        widget=CheckboxSelectMultiple
    )
    date = DateField(
        initial=date.today,
        widget=SelectDateWidget()
    )

    form_action = ""

    class Meta:
        model = CinemaProvider
        fields = ["cinema", "date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "POST"
        self.helper.form_action = self.form_action
        self.fields["cinema"].label = ""
        self.fields["date"].label = ""

        self.helper.layout = Layout(
            Div(
                Field("cinema", wrapper_class="col-auto"),
                Field("date", wrapper_class="col-4 row", css_class="col"),
                Div(
                    HTML("<button id='start-scan-btn' class='btn btn-outline-warning btn-lg col' type='button'>"
                         "Start Scan!</button>"),
                    css_class="col-auto mt-1"
                ),
                css_class="row justify-content-md-center"
            ),
        )
