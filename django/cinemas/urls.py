from django.urls import path

from cinemas.views import (
    MainTemplateView,
    GetScraperStatusView, CSVDownloadView,
)

urlpatterns = [
    path("", MainTemplateView.as_view(), name="main"),
    path("get_scraper_status", GetScraperStatusView.as_view(), name="get_scraper_status"),
    path("get_csv/<uuid:pk>", CSVDownloadView.as_view(), name="get_csv")
]
