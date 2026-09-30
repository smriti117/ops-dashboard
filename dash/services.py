""" Db related queries & """
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from .models import Transaction, Venue, VenueHourlyStats, VenueItemStats

# Alert tuning
DROP_RATIO = 0.5           # last hour < 50% of the venue's recent hourly average
MIN_BASELINE_HOURLY = 100  # ignore venues with tiny baselines (avoids noise)
BAD_RATE = 0.15            # (voids + refunds) / transactions
MIN_TX = 10                # minimum volume before a void spike can fire


def _bump(model, lookup, deltas, defaults=None):
    """Create the row if missing, then increment atomically in SQL (F() = no lost updates)."""
    obj, _ = model.objects.get_or_create(**lookup, defaults=defaults or {})
    model.objects.filter(pk=obj.pk).update(**{k: F(k) + v for k, v in deltas.items()})


def ingest(venue, d):
    """Store one transaction + update aggregates atomically. Returns False for duplicates."""
    local = timezone.localtime(d["timestamp"])
    hour = local.replace(minute=0, second=0, microsecond=0)
    items = [{**i, "price": str(i["price"])} for i in d["items"]]
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint so a duplicate doesn't poison the outer txn
                Transaction.objects.create(
                    venue=venue, transaction_id=d["transaction_id"], timestamp=d["timestamp"],
                    type=d["type"], total=d["total"], staff_id=d["staff_id"], items=items)
        except IntegrityError:
            return False  # POS retry: unique transaction_id already stored, don't double count
        key = {"venue": venue, "hour_start": hour}
        if d["type"] == "sale":
            _bump(VenueHourlyStats, key, {"sales_total": d["total"], "sale_count": 1})
            for i in d["items"]:
                _bump(VenueItemStats, {"venue": venue, "date": local.date(), "item_id": i["item_id"]},
                      {"qty": i["qty"], "revenue": i["qty"] * i["price"]}, defaults={"item_name": i["name"]})
        elif d["type"] == "refund":
            _bump(VenueHourlyStats, key, {"refund_total": d["total"], "refund_count": 1})
        else:
            _bump(VenueHourlyStats, key, {"void_count": 1})
    return True


def compute_alerts(r):
    """Pure function: r is one venue's recent-window aggregate (or None)."""
    if not r:
        return []
    alerts = []
    baseline = float(r["base_sales"] or 0) / 3  # avg hourly sales over hours 1-4 ago
    if baseline >= MIN_BASELINE_HOURLY and float(r["recent_sales"] or 0) < DROP_RATIO * baseline:
        alerts.append("sales_drop")
    n = r["recent_count"]
    if n >= MIN_TX and r["recent_bad"] / n > BAD_RATE:
        alerts.append("void_spike")
    return alerts


def _today(now=None):
    start = timezone.localtime(now or timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start.date()


def build_snapshot():
    now = timezone.now()
    day_start, today = _today(now)
    hour_ago = now - timedelta(hours=1)

    net = {r["venue_id"]: (r["s"] or 0) - (r["r"] or 0) for r in
           VenueHourlyStats.objects.filter(hour_start__gte=day_start)
           .values("venue_id").annotate(s=Sum("sales_total"), r=Sum("refund_total"))}

    recent = {r["venue_id"]: r for r in
              Transaction.objects.filter(timestamp__gte=now - timedelta(hours=4)).values("venue_id").annotate(
                  recent_sales=Sum("total", filter=Q(type="sale", timestamp__gte=hour_ago)),
                  recent_count=Count("id", filter=Q(timestamp__gte=hour_ago)),
                  recent_bad=Count("id", filter=Q(type__in=["void", "refund"], timestamp__gte=hour_ago)),
                  base_sales=Sum("total", filter=Q(type="sale", timestamp__lt=hour_ago)))}

    venues = [{"code": v.code, "name": v.name, "venue_type": v.venue_type,
               "sales_today": float(net.get(v.id, 0)), "alerts": compute_alerts(recent.get(v.id))}
              for v in Venue.objects.all()]
    venues.sort(key=lambda v: -v["sales_today"])

    top = VenueItemStats.objects.filter(date=today).values("item_name").annotate(qty=Sum("qty")).order_by("-qty")[:10]
    return {"generated_at": now.isoformat(), "group_total": sum(v["sales_today"] for v in venues),
            "venues": venues, "top_items": list(top)}


def venue_detail(venue):
    day_start, today = _today()
    hourly = VenueHourlyStats.objects.filter(venue=venue, hour_start__gte=day_start).order_by("hour_start")
    items = (VenueItemStats.objects.filter(venue=venue, date=today)
             .values("item_name", "qty").order_by("-qty")[:10])
    return {"code": venue.code, "name": venue.name,
            "hourly": [{"hour": h.hour_start.isoformat(), "net_sales": float(h.sales_total - h.refund_total),
                        "transactions": h.sale_count + h.void_count + h.refund_count} for h in hourly],
            "top_items": list(items)}
