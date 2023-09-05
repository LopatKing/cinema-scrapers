from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class ScraperStatus(TextChoices):
    AVAILABLE = "AV", _("Available")
    IN_PROGRESS = "IP", _("In progress")
