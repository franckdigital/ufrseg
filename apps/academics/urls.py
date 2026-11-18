from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("annees", views.AnneeViewSet)
router.register("filieres", views.FiliereViewSet)
router.register("parcours", views.ParcoursViewSet)
router.register("classes", views.ClasseViewSet)
router.register("ues", views.UEViewSet)
router.register("ecues", views.ECUEViewSet)
router.register("regles-validation", views.RegleViewSet)
router.register("simulateur", views.SimulateurView, basename="simulateur")
urlpatterns = router.urls
