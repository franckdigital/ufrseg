from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("annonces", views.AnnonceViewSet, basename="annonce")
router.register("evenements", views.EvenementViewSet)
router.register("faq", views.FAQViewSet)
router.register("offres", views.OffreViewSet)
router.register("notifications", views.NotificationViewSet, basename="notification")
urlpatterns = [
    path("contact/", views.ContactView.as_view()),
    path("assistant/ask/", views.AssistantView.as_view()),
    path("public/stats/", views.PublicStatsView.as_view()),
] + router.urls
