from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("groupes", views.GroupeViewSet, basename="groupe")
router.register("devoirs", views.DevoirViewSet, basename="devoir")
router.register("evaluations", views.EvaluationViewSet, basename="evaluation")
router.register("notes", views.NoteViewSet, basename="note")
urlpatterns = router.urls
