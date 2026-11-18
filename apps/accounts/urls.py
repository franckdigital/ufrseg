from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("register/", views.RegisterView.as_view()),
    path("login/", views.LoginView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", views.MeView.as_view()),
    path("change-secret/", views.ChangeSecretView.as_view()),
    path("classmates/", views.ClassmatesView.as_view()),
    path("roles/", views.RolesView.as_view()),
    path("system/", views.SystemView.as_view()),
    path("", include(router.urls)),
]
