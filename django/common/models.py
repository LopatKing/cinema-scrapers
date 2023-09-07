from django.db import models
import uuid


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Country(models.Model):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )


class Error(TimestampedModel):
    title = models.TextField(
        blank=False,
        null=False
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ["-created_on"]
