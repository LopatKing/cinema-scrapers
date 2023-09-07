from django.contrib import admin

from common.models import Error


@admin.register(Error)
class CinemaProviderAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "source",
        "created_on",
    ]
    list_filter = ["source", "created_on"]
