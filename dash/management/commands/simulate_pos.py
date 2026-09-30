import random
import time
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from dash.models import Venue

MENU = [("P1", "Lager pint", 9.5), ("P2", "Pale ale", 11), ("F1", "Burger", 22), ("F2", "Fish & chips", 24),
        ("F3", "Caesar salad", 18), ("D1", "Flat white", 5), ("D2", "Wine glass", 12), ("F4", "Nachos", 16),
        ("D3", "Cola", 4.5), ("F5", "Steak", 38)]


def make_tx(code, ts, bad_rate):
    r = random.random()
    typ = "void" if r < bad_rate * 0.6 else "refund" if r < bad_rate else "sale"
    items = [{"item_id": i[0], "name": i[1], "qty": random.randint(1, 3), "price": i[2]}
             for i in random.sample(MENU, random.randint(1, 4))]
    return {"venue_id": code, "transaction_id": str(uuid.uuid4()), "timestamp": ts.isoformat(), "type": typ,
            "items": items, "total": round(sum(x["qty"] * x["price"] for x in items), 2),
            "staff_id": f"S{random.randint(1, 20)}"}


class Command(BaseCommand):
    help = "Fake POS: backfills 4h of history, then streams live transactions to the real ingest endpoint."

    def add_arguments(self, p):
        p.add_argument("--url", default="http://localhost:8000/api/transactions/")
        p.add_argument("--interval", type=float, default=0.5)

    def handle(self, *a, url, interval, **o):
        s = requests.Session()
        s.headers["X-API-Key"] = settings.POS_API_KEY
        codes = list(Venue.objects.values_list("code", flat=True))
        weight = {c: random.uniform(0.3, 1.0) for c in codes}  # busy vs quiet venues
        quiet, hot = set(random.sample(codes, 2)), set(random.sample(codes, 2))  # demo alerts
        self.stdout.write(f"Quiet (sales drop): {sorted(quiet)}  Hot (void spike): {sorted(hot)}")

        def post(tx):
            try:
                s.post(url, json=tx, timeout=5).raise_for_status()
            except requests.RequestException as e:
                self.stderr.write(f"post failed: {e}")

        now = timezone.now()
        for h in (4, 3, 2, 1):  # h=1 is the most recent hour; scenarios apply there
            for c in codes:
                n = int(weight[c] * 100 * (0.2 if c in quiet and h == 1 else 1))
                for _ in range(n):
                    ts = now - timedelta(hours=h) + timedelta(seconds=random.uniform(0, 3600))
                    post(make_tx(c, ts, 0.4 if c in hot and h == 1 else 0.08))
        self.stdout.write("Backfill done. Streaming live (Ctrl+C to stop)...")
        while True:
            for c in codes:
                per_hour = weight[c] * 100 * (0.2 if c in quiet else 1)
                if random.random() < per_hour / 3600 * interval:
                    post(make_tx(c, timezone.now(), 0.4 if c in hot else 0.08))
            time.sleep(interval)
