import csv
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from cinemas.constants import ScraperStatus
from cinemas.forms import StartScraperForm
from cinemas.models import CinemaProvider, ScraperTask, ShowtimeSeats
from cinemas.tasks import scan_cinema


class MainTemplateView(TemplateView):
    template_name = "index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["start_scraper_form"] = StartScraperForm()
        return context


class GetScraperStatusView(View):

    def post(self, request, *args, **kwargs):
        cinema_pk = self.request.POST.get('cinema_id')
        date_str = self.request.POST.get('date')
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        cinema_provider_obj = CinemaProvider.objects.get(pk=cinema_pk)
        last_task = ScraperTask.objects.filter(cinema_provider=cinema_provider_obj, date_query=date_obj).order_by("created_on").last()

        if cinema_provider_obj.scraper_status == ScraperStatus.IN_PROGRESS:
            return JsonResponse({"status": ScraperStatus.IN_PROGRESS.name}, status=202)
        if not last_task:
            self.run_scraper(cinema_provider_obj, date_obj)
            return JsonResponse({"status": ScraperStatus.IN_PROGRESS.name}, status=202)

        last_scan_on = last_task.created_on
        now = timezone.now()
        timedelta_ = now - last_scan_on
        if timedelta_.seconds > settings.SCRAPERS_CACHE_TIME:
            self.run_scraper(cinema_provider_obj, date_obj)
            return JsonResponse({"status": ScraperStatus.IN_PROGRESS.name}, status=202)
        return JsonResponse({"status": ScraperStatus.AVAILABLE.name, "task_id": last_task.pk}, status=200)

    def run_scraper(self, cinema_obj: CinemaProvider, date: datetime.date):
        cinema_obj.scraper_status = ScraperStatus.IN_PROGRESS
        cinema_obj.save()
        scan_cinema.delay(cinema_obj.pk, date)


class CSVDownloadView(View):

    def get(self, *args, **kwargs):
        task_id = self.kwargs['pk']
        task = ScraperTask.objects.get(id=task_id)
        filename = f"{task.cinema_provider.name}.csv"
        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

        seats = ShowtimeSeats.objects.filter(task=task)
        headers = [
            "Movie",
            "Cinema",
            "Date/Time",
            "Experience",
            "Cinema Room",
            "Seats Area",
            "All",
            "Sold",
            "URL",
            "Parsed on",
            "Language"
        ]
        writer = csv.writer(response)
        writer.writerow(headers)
        for seat_obj in seats:
            writer.writerow([
                seat_obj.movie.name,
                seat_obj.cinema.name,
                seat_obj.datetime.strftime("%d %B %H:%M"),
                seat_obj.experience,
                seat_obj.cinema_room,
                seat_obj.area,
                seat_obj.all,
                seat_obj.sold,
                seat_obj.url,
                seat_obj.created_on.strftime("%d %B %H:%M"),
                seat_obj.movie.language,
            ])
        return response



