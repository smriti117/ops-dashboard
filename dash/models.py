from django.db import models


class Venue(models.Model):
    class VenueType(models.TextChoices):
        PUB = "pub"
        RESTAURANT = "restaurant"
        FUNCTION = "function_space"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    venue_type = models.CharField(max_length=20, choices=VenueType.choices)

    def __str__(self):
        return self.code


class Transaction(models.Model):
    """Raw records"""

    class Type(models.TextChoices):
        SALE = "sale"
        VOID = "void"
        REFUND = "refund"

    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="transactions")
    transaction_id = models.CharField(max_length=64, unique=True)  # makes ingest idempotent
    timestamp = models.DateTimeField()  # when it happened at the POS
    type = models.CharField(max_length=10, choices=Type.choices)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    staff_id = models.CharField(max_length=32)
    items = models.JSONField(default=list)
    received_at = models.DateTimeField(auto_now_add=True)  # when we got it (spot late POS data)

    class Meta:
        indexes = [models.Index(fields=["venue", "timestamp"]), models.Index(fields=["timestamp"])]


class VenueHourlyStats(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    hour_start = models.DateTimeField()
    sales_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sale_count = models.IntegerField(default=0)
    void_count = models.IntegerField(default=0)
    refund_count = models.IntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["venue", "hour_start"], name="uniq_venue_hour")]


class VenueItemStats(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    date = models.DateField()
    item_id = models.CharField(max_length=64)
    item_name = models.CharField(max_length=200)
    qty = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["venue", "date", "item_id"], name="uniq_venue_date_item")]
