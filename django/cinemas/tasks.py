import importlib
import random
import time
from datetime import datetime

from cinemas.constants import ScraperStatus
from cinemas.models import CinemaProvider, ScraperTask
from config.celery import app


@app.task
def scan_cinema(cinema_provider_pk: str, date_query: datetime.date) -> bool:
    cinema_provider_obj = CinemaProvider.objects.get(pk=cinema_provider_pk)
    task = ScraperTask.objects.create(cinema_provider=cinema_provider_obj, date_query=date_query)

    scraper_module_str = cinema_provider_obj.scraper_file.replace("/", ".")[0:-3]
    scraper_module = importlib.import_module(scraper_module_str)
    scraper_module.save_to_django_db(task)

    cinema_provider_obj.scraper_status = ScraperStatus.AVAILABLE
    cinema_provider_obj.save()
    return True
