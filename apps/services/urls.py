from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("demandes", views.DemandeViewSet, basename="demande")
router.register("frais-services", views.FraisViewSet, basename="frais")
router.register("rendez-vous", views.RdvViewSet, basename="rdv")
urlpatterns = [path("dashboard/", views.DashboardView.as_view())] + router.urls
