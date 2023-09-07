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
            Field("cinema", wrapper_class="d-flex justify-content-center", css_class="h5 d-lg-flex justify-content-center"),
            Field("date", wrapper_class="d-flex justify-content-center"),
            Div(
                HTML("<button id='start-scan-btn' class='btn btn-lg' type='button'>Start Scan!</button>"),
                css_class="d-flex justify-content-center"
            ),
            HTML(
                """
                {% for cinema_providers in cinema_providers %}
                    <img src="{{ cinema_providers.logo.url }}" value="{{ cinema_providers.id }}" class="d-none logo">
                {% endfor %}
                """
            )
        )
