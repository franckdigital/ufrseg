from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("plans", views.PlanViewSet)
router.register("finance", views.FinanceViewSet, basename="finance")

urlpatterns = [
    path("billing/subscription/", views.MySubscriptionView.as_view()),
    path("billing/checkout/", views.CheckoutView.as_view()),
    path("billing/payments/", views.MyPaymentsView.as_view()),
    path("billing/payments/<uuid:reference>/sandbox-confirm/", views.SimulateConfirmView.as_view()),
    path("billing/payments/<uuid:reference>/verify/", views.VerifyPaymentView.as_view()),
    path("billing/cinetpay-webhook/", views.CinetPayWebhookView.as_view()),
    path("billing/webhook/", views.PaymentWebhookView.as_view()),
    path("billing/author/", views.AuthorView.as_view()),
] + router.urls
