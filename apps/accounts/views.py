from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import IsBackOffice
from .roles import FEATURES, MANAGE, ROLES, can_manage, generate_secret
from .serializers import (ChangeSecretSerializer, LoginSerializer, RegisterSerializer, UserAdminSerializer, UserSerializer)


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
    """Back-office : gestion des comptes. Enseignants : lecture seule de la liste des étudiants (saisie des notes)."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return u.is_back_office or (u.role == "ENSEIGNANT" and request.method in permissions.SAFE_METHODS)


class UserViewSet(viewsets.ModelViewSet):
    """CRUD des comptes avec contrôle hiérarchique des rôles (voir roles.MANAGE)."""

    queryset = User.objects.select_related("classe").all()
    permission_classes = [UserPermission]
    filterset_fields = ["role", "is_author", "is_active", "classe"]
    search_fields = ["first_name", "last_name", "phone", "email", "matricule"]
    ordering_fields = ["last_name", "date_joined", "last_login"]

    def get_serializer_class(self):
        return UserAdminSerializer if self.request.user.is_back_office else UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.request.user.is_back_office else qs.filter(role="ETUDIANT", is_active=True)

    def _check_target(self, target):
        if not can_manage(self.request.user.role, target.role):
            raise PermissionDenied("Vous n'avez pas le droit de gérer ce compte.")

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        role = d.get("role", "ETUDIANT")
        secret = d.pop("password", "") or ""
        generated = not secret
        if generated:
            secret = generate_secret(role)
        extra = {k: d[k] for k in ("email", "matricule", "is_author", "is_class_rep", "classe", "is_active") if k in d}
        user = User.objects.create_user(d["phone"], secret, first_name=d["first_name"].strip(), last_name=d["last_name"].strip(), role=role,
                                        has_pin=secret.isdigit() and 4 <= len(secret) <= 6, **extra)
        data = UserAdminSerializer(user, context=self.get_serializer_context()).data
        # Le secret n'est renvoyé qu'ici, une seule fois, quand il a été généré par le serveur.
        data["generated_secret"] = secret if generated else None
        return Response(data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        self._check_target(self.get_object())
        if self.get_object().pk == request.user.pk and any(k in request.data for k in ("role", "is_active")):
            raise PermissionDenied("Vous ne pouvez pas modifier votre propre rôle ni désactiver votre compte.")
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        user = serializer.save()
        pw = self.request.data.get("password")
        if pw:
            user.set_password(pw)
            user.has_pin = pw.isdigit() and 4 <= len(pw) <= 6
            user.save(update_fields=["password", "has_pin"])

    def destroy(self, request, *args, **kwargs):
        """Désactivation (jamais de suppression : l'historique des paiements, notes et dossiers est conservé)."""
        u = self.get_object()
        self._check_target(u)
        if u.pk == request.user.pk:
            raise PermissionDenied("Vous ne pouvez pas désactiver votre propre compte.")
        if u.role == "ADMIN" and User.objects.filter(role="ADMIN", is_active=True).exclude(pk=u.pk).count() == 0:
            raise PermissionDenied("Impossible de désactiver le dernier administrateur.")
        u.is_active = False
        u.save(update_fields=["is_active"])
        return Response({"detail": "Compte désactivé.", "id": u.pk})

    @action(detail=True, methods=["post"], url_path="reset-secret")
    def reset_secret(self, request, pk=None):
        """Nouveau PIN / mot de passe (généré ou fourni). Renvoyé une seule fois."""
        u = self.get_object()
        self._check_target(u)
        given = (request.data.get("secret") or "").strip()
        if given and len(given) < 4:
            return Response({"detail": "Minimum 4 caractères."}, status=400)
        secret = given or generate_secret(u.role)
        u.set_password(secret)
        u.has_pin = secret.isdigit() and 4 <= len(secret) <= 6
        u.save(update_fields=["password", "has_pin"])
        return Response({"secret": secret, "generated": not given})


class RolesView(APIView):
    """Rôles, droits de gestion du demandeur et matrice des permissions."""

    permission_classes = [IsBackOffice]

    def get(self, request):
        return Response({
            "roles": [{"code": k, "label": v[0], "description": v[1]} for k, v in ROLES.items()],
            "can_manage": sorted(MANAGE.get(request.user.role, set())),
            "features": [{"group": g, "label": l, "roles": r} for g, l, r in FEATURES],
        })


class SystemView(APIView):
    """État technique (administrateur général) : permet de vérifier la base réellement utilisée par le service."""

    permission_classes = [IsBackOffice]

    def get(self, request):
        if request.user.role != "ADMIN":
            raise PermissionDenied()
        from django.conf import settings

        d = settings.DATABASES["default"]
        return Response({"database": {"engine": d["ENGINE"].split(".")[-1], "name": str(d["NAME"]), "host": d.get("HOST") or "local"},
                         "users": User.objects.count(), "debug": settings.DEBUG})
