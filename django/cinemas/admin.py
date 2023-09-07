from django.contrib import admin
from django.utils.safestring import mark_safe

from cinemas.models import CinemaProvider, ShowtimeSeats


@admin.register(CinemaProvider)
class CinemaProviderAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "url",
        "is_available",
        "scraper_status",
    ]
    list_editable = ("is_available",)
    readonly_fields = ["scraper_status"]


@admin.register(ShowtimeSeats)
class ShowtimeSeatsAdmin(admin.ModelAdmin):
    list_display = [
        "get_cinema_provider_name",
        "created_on",
        "get_csv_by_task",
    ]
    list_filter = [
        "task__cinema_provider"
    ]
    readonly_fields = ["get_csv_by_task"]

    @staticmethod
    def get_csv_by_task(object):
        return mark_safe(f"<a href='/get_csv/{object.task.id}'>Get csv by task</a>")

    def get_cinema_provider_name(self, object):
        return object.task.cinema_provider.name
    get_cinema_provider_name.short_description = "Cinema Provider"

