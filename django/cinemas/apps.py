from django.apps import AppConfig

from cinemas.constants import ScraperStatus


class CinemasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cinemas'

    def ready(self):
        try:
            cinema_provider = self.get_model("CinemaProvider")
            cinemas = cinema_provider.objects.all()
            for cinema in cinemas:
                cinema.scraper_status = ScraperStatus.AVAILABLE
                cinema.save()
        except:
            return
