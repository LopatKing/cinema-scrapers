from common.models import TimestampedModel, Country
from django.db import models

from cinemas.constants import ScraperStatus


class CinemaProvider(TimestampedModel):
    name = models.CharField(
        blank=False,
        null=False,
        max_length=255,
        help_text="Displayed in the selection form for the user"
    )
    url = models.URLField(
        blank=True,
    )
    is_available = models.BooleanField(
        default=False,
        verbose_name="available for users?"
    )
    scraper_status = models.CharField(
        max_length=2,
        choices=ScraperStatus.choices,
        null=False,
        blank=False,
        editable=False,
        default=ScraperStatus.AVAILABLE,
        verbose_name="Scraper status"
    )
    scraper_file = models.FilePathField(
        blank=False,
        null=False,
        help_text='The file must be in the "scrapers" folder',
        path="scrapers",
        match=".*\.py$",
        recursive=True
    )
    logo = models.ImageField(
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Cinema Provider"
        verbose_name_plural = "Cinema Providers"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ScraperTask(TimestampedModel):
    cinema_provider = models.ForeignKey(
        CinemaProvider,
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )
    date_query = models.DateField(
        blank=False,
        null=False,
        help_text="Scraper looks for data for this date"
    )


class Cinema(TimestampedModel):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name


class Movie(TimestampedModel):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    language = models.CharField(
        max_length=255,
        blank=True,
    )

    def __str__(self):
        return self.name


class ShowtimeSeats(TimestampedModel):
    task = models.ForeignKey(
        ScraperTask,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    cinema = models.ForeignKey(
        Cinema,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    datetime = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="Showtime datetime"
    )
    url = models.URLField(
        blank=True,
        verbose_name="Showtime page url"
    )
    experience = models.CharField(
        max_length=255,
        blank=True
    )
    all = models.PositiveIntegerField(
        blank=False,
        null=False,
        verbose_name="All seats"
    )
    sold = models.PositiveIntegerField(
        blank=False,
        null=False,
        verbose_name="Sold seats"
    )
    cinema_room = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Seats screen"
    )
    price = models.DecimalField(
        blank=False,
        null=False,
        decimal_places=2,
        max_digits=6,
    )
    area = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Seats area"
    )

    class Meta:
        verbose_name = "Showtime Seats"
        verbose_name_plural = "Showtime Seats"
        ordering = ["-created_on"]

    def __str__(self):
        return f"{self.task.cinema_provider.name} - {self.created_on.strftime('%d %B %H:%M')}"
