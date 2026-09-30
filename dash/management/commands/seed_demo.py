from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from dash.models import Venue

ADJ = ["Royal", "Old", "Golden", "Red", "Salty", "Grand", "Lucky", "Iron"]
NOUN = ["Oak", "Crown", "Anchor", "Fox", "Harbour"]
KINDS = ["pub", "restaurant", "function_space"]


class Command(BaseCommand):
    help = "Create 40 venues and an ops user (ops / ops12345)"

    def handle(self, *a, **o):
        for i in range(1, 41):
            Venue.objects.get_or_create(code=f"V{i:02d}", defaults={
                "name": f"{ADJ[i % 8]} {NOUN[i % 5]} #{i}", "venue_type": KINDS[i % 3]})
        if not User.objects.filter(username="ops").exists():
            User.objects.create_user("ops", password="ops12345")
        self.stdout.write("Seeded 40 venues, user ops / ops12345")
