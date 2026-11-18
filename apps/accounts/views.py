from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import IsBackOffice
from .serializers import ChangeSecretSerializer, LoginSerializer, RegisterSerializer, UserSerializer


def _tokens(user):
    r = RefreshToken.for_user(user)
    return {"access": str(r.access_token), "refresh": str(r), "user": UserSerializer(user).data}


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return Response(_tokens(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(_tokens(s.validated_data["user"]))


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangeSecretView(APIView):
    def post(self, request):
        s = ChangeSecretSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if not request.user.check_password(s.validated_data["old_secret"]):
            return Response({"detail": "Ancien code incorrect."}, status=400)
        request.user.set_password(s.validated_data["new_secret"])
        request.user.has_pin = len(s.validated_data["new_secret"]) <= 6 and s.validated_data["new_secret"].isdigit()
        request.user.save()
        return Response({"detail": "Code mis à jour."})


class ClassmatesView(APIView):
    """Camarades de la même classe (id + nom uniquement) — utilisé pour inviter dans un groupe."""

    def get(self, request):
        if not request.user.classe_id:
            return Response([])
        rows = User.objects.filter(classe_id=request.user.classe_id, role="ETUDIANT", is_active=True).exclude(pk=request.user.pk)
        return Response([{"id": u.id, "full_name": u.full_name} for u in rows])


class UserPermission(permissions.BasePermission):
    """Back-office : tout. Enseignants : lecture seule (saisie des notes)."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return u.is_back_office or (u.role == "ENSEIGNANT" and request.method in permissions.SAFE_METHODS)


class UserViewSet(viewsets.ModelViewSet):
    """Administration des comptes (back-office) ; lecture pour les enseignants."""

    queryset = User.objects.select_related("classe").all()
    serializer_class = UserSerializer
    permission_classes = [UserPermission]
    filterset_fields = ["role", "is_author", "is_active", "classe"]
    search_fields = ["first_name", "last_name", "phone", "email", "matricule"]

    def perform_create(self, serializer):
        # Création par le back-office : PIN initial = 4 derniers chiffres du téléphone.
        phone = self.request.data.get("phone", "")
        user = serializer.save()
        user.phone = user.phone or phone
        user.set_password(self.request.data.get("password") or user.phone[-4:])
        user.save()
