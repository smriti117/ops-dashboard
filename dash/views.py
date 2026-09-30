import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from . import services
from .models import Venue
from .serializers import TransactionSerializer


class HasApiKey(BasePermission):
    """POS systems authenticate with a shared key (constant-time compare), not user tokens."""
    def has_permission(self, request, view):
        return hmac.compare_digest(request.headers.get("X-API-Key", ""), settings.POS_API_KEY)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([HasApiKey])
def ingest(request):
    s = TransactionSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    venue = Venue.objects.filter(code=d["venue_id"]).first()
    if venue is None:
        return Response({"venue_id": "unknown venue"}, status=400)
    created = services.ingest(venue, d)
    return Response({"status": "created" if created else "duplicate"}, status=201 if created else 200)


@api_view(["GET"])
def snapshot(request):  # REST fallback / same payload the WebSocket pushes
    return Response(services.build_snapshot())


@api_view(["GET"])
def venue_detail(request, code):
    return Response(services.venue_detail(get_object_or_404(Venue, code=code)))
