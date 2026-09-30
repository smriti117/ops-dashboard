from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from dash import views

urlpatterns = [
    path("api/auth/login/", obtain_auth_token),
    path("api/transactions/", views.ingest),
    path("api/dashboard/snapshot/", views.snapshot),
    path("api/venues/<str:code>/", views.venue_detail),
]
