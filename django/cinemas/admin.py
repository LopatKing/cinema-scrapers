from django.contrib import admin

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
    pass

