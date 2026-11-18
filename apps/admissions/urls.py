from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("guides", views.GuideViewSet, basename="guide")
router.register("programmes", views.ProgrammeViewSet, basename="programme")
router.register("candidatures", views.CandidatureViewSet, basename="candidature")
urlpatterns = router.urls
