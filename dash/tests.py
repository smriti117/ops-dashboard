from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from . import services
from .models import Transaction, Venue, VenueHourlyStats


class AlertTests(TestCase):
    def test_sales_drop(self):
        r = {"base_sales": 900, "recent_sales": 50, "recent_count": 5, "recent_bad": 0}
        self.assertEqual(services.compute_alerts(r), ["sales_drop"])

    def test_void_spike_needs_min_volume(self):
        r = {"base_sales": 0, "recent_sales": 0, "recent_count": 3, "recent_bad": 3}
        self.assertEqual(services.compute_alerts(r), [])

    def test_void_spike(self):
        r = {"base_sales": 0, "recent_sales": 0, "recent_count": 20, "recent_bad": 8}
        self.assertEqual(services.compute_alerts(r), ["void_spike"])


class IngestTests(TestCase):
    def setUp(self):
        self.v = Venue.objects.create(code="V1", name="A", venue_type="pub")
        self.d = {"transaction_id": "t1", "timestamp": timezone.now(), "type": "sale", "total": Decimal("20.00"),
                  "staff_id": "S1", "items": [{"item_id": "P1", "name": "Lager", "qty": 2, "price": Decimal("10.00")}]}

    def test_idempotent(self):
        self.assertTrue(services.ingest(self.v, self.d))
        self.assertFalse(services.ingest(self.v, self.d))  # retry must not double count
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(VenueHourlyStats.objects.get().sale_count, 1)

    def test_refund_reduces_net(self):
        services.ingest(self.v, self.d)
        services.ingest(self.v, {**self.d, "transaction_id": "t2", "type": "refund", "total": Decimal("5.00")})
        snap = services.build_snapshot()
        self.assertEqual(snap["venues"][0]["sales_today"], 15.0)
