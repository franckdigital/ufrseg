import random
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Q
from django.utils import timezone
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsTeacherOrBackOffice

from apps.accounts.files import SignedFilesMixin
from .grading import grade_copy
from .models import (Copie, Devoir, Evaluation, Groupe, MembreGroupe, MessageGroupe, Note, Question, Soumission)


def is_staff_like(u):
    return u.is_back_office or u.role == "ENSEIGNANT"


# ───────────────────────── Groupes ─────────────────────────
class GroupeSerializer(serializers.ModelSerializer):
    nb_membres = serializers.SerializerMethodField()
    membres_noms = serializers.SerializerMethodField()
    est_membre = serializers.SerializerMethodField()

    class Meta:
        model = Groupe
        fields = ["id", "classe", "nom", "description", "responsable", "ue", "max_membres", "nb_membres", "membres_noms", "est_membre"]
        read_only_fields = ["responsable"]

    def get_nb_membres(self, g):
        return g.membres.filter(statut="ACTIF").count()

    def get_membres_noms(self, g):
        return [m.user.full_name for m in g.membres.filter(statut="ACTIF").select_related("user")]

    def get_est_membre(self, g):
        return g.membres.filter(user=self.context["request"].user, statut="ACTIF").exists()


class GroupeViewSet(viewsets.ModelViewSet):
    serializer_class = GroupeSerializer
    filterset_fields = ["classe", "ue"]

    def get_queryset(self):
        u = self.request.user
        qs = Groupe.objects.all()
        return qs if is_staff_like(u) else qs.filter(classe=u.classe)

    def perform_create(self, serializer):
        u = self.request.user
        classe = serializer.validated_data["classe"]
        if u.role == "ETUDIANT" and u.classe_id != classe.id:
            raise PermissionDenied("Vous ne pouvez créer un groupe que dans votre classe.")
        g = serializer.save(responsable=u)
        MembreGroupe.objects.create(groupe=g, user=u)

    @action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        g = self.get_object()
        if g.responsable_id != request.user.id and not is_staff_like(request.user):
            raise PermissionDenied("Réservé au responsable du groupe.")
        from apps.accounts.models import User
        target = User.objects.filter(pk=request.data.get("user"), classe=g.classe).first()
        if not target:
            raise ValidationError("Étudiant introuvable dans cette classe.")
        if g.membres.filter(statut="ACTIF").count() >= g.max_membres:
            raise ValidationError("Groupe complet.")
        MembreGroupe.objects.get_or_create(groupe=g, user=target, defaults={"statut": "INVITE"})
        return Response({"ok": True}, status=201)

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """Accepter une invitation ou rejoindre un groupe de sa classe."""
        g = self.get_object()
        if g.membres.filter(statut="ACTIF").count() >= g.max_membres:
            raise ValidationError("Groupe complet.")
        m, _ = MembreGroupe.objects.get_or_create(groupe=g, user=request.user)
        m.statut = "ACTIF"
        m.save()
        return Response({"ok": True})

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        g = self.get_object()
        if not g.membres.filter(user=request.user, statut="ACTIF").exists() and not is_staff_like(request.user):
            raise PermissionDenied()
        if request.method == "POST":
            MessageGroupe.objects.create(groupe=g, auteur=request.user, texte=request.data.get("texte", "")[:2000])
        rows = g.messages.select_related("auteur").values("id", "texte", "created", "auteur__first_name", "auteur__last_name")[:200]
        return Response(list(rows))


# ───────────────────────── Devoirs / TD ─────────────────────────
class SoumissionSerializer(SignedFilesMixin, serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source="auteur.full_name", read_only=True)

    class Meta:
        model = Soumission
        fields = ["id", "devoir", "auteur", "auteur_nom", "groupe", "fichier", "commentaire", "en_retard", "note", "appreciation", "created"]
        read_only_fields = ["auteur", "en_retard", "note", "appreciation"]


class DevoirSerializer(SignedFilesMixin, serializers.ModelSerializer):
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    ma_soumission = serializers.SerializerMethodField()
    nb_soumissions = serializers.IntegerField(source="soumissions.count", read_only=True)

    class Meta:
        model = Devoir
        fields = "__all__"
        read_only_fields = ["cree_par"]

    def get_ma_soumission(self, d):
        s = d.soumissions.filter(auteur=self.context["request"].user).first()
        return SoumissionSerializer(s).data if s else None


class DevoirViewSet(viewsets.ModelViewSet):
    serializer_class = DevoirSerializer
    filterset_fields = ["classe", "ecue", "en_groupe"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "soumettre"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrBackOffice()]

    def get_queryset(self):
        u = self.request.user
        qs = Devoir.objects.select_related("classe")
        return qs if is_staff_like(u) else qs.filter(classe=u.classe)

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        d = self.get_object()
        f = request.FILES.get("fichier")
        if not f:
            raise ValidationError("Fichier requis.")
        late = timezone.now() > d.date_limite
        s, _ = Soumission.objects.update_or_create(devoir=d, auteur=request.user, defaults={
            "fichier": f, "commentaire": request.data.get("commentaire", ""), "en_retard": late,
            "groupe_id": request.data.get("groupe") or None})
        return Response(SoumissionSerializer(s).data, status=201)

    @action(detail=True, methods=["get"])
    def soumissions(self, request, pk=None):
        if not is_staff_like(request.user):
            raise PermissionDenied()
        d = self.get_object()
        return Response(SoumissionSerializer(d.soumissions.select_related("auteur"), many=True).data)

    @action(detail=True, methods=["post"], url_path="noter/(?P<sid>[0-9]+)")
    def noter(self, request, pk=None, sid=None):
        if not is_staff_like(request.user):
            raise PermissionDenied()
        s = Soumission.objects.get(pk=sid, devoir_id=pk)
        s.note, s.appreciation = request.data.get("note"), request.data.get("appreciation", "")
        s.save()
        return Response(SoumissionSerializer(s).data)


# ───────────────────────── Évaluations ─────────────────────────
class QuestionStudentSerializer(serializers.ModelSerializer):
    """Vue étudiant : sans la réponse attendue."""

    class Meta:
        model = Question
        fields = ["id", "type", "enonce", "options", "bareme", "ordre"]


class QuestionFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = "__all__"


class EvaluationSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    ecue_intitule = serializers.CharField(source="ecue.intitule", read_only=True, default=None)
    nb_questions = serializers.IntegerField(source="questions.count", read_only=True)
    total_points = serializers.SerializerMethodField()
    ma_copie = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = "__all__"
        read_only_fields = ["cree_par"]

    def get_total_points(self, e):
        return float(e.total_points())

    def get_ma_copie(self, e):
        c = e.copies.filter(etudiant=self.context["request"].user).order_by("-tentative").first()
        if not c:
            return None
        show = e.resultats_publies or is_staff_like(self.context["request"].user)
        return {"id": c.id, "statut": c.statut, "note": float(c.note_finale) if (show and c.note_finale is not None) else None}


class EvaluationViewSet(viewsets.ModelViewSet):
    serializer_class = EvaluationSerializer
    filterset_fields = ["classe", "ecue", "type", "publie"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "demarrer", "repondre", "soumettre", "journal"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrBackOffice()]

    def get_queryset(self):
        u = self.request.user
        qs = Evaluation.objects.select_related("classe", "ecue")
        return qs if is_staff_like(u) else qs.filter(classe=u.classe, publie=True)

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["get", "post"])
    def questions(self, request, pk=None):
        if not is_staff_like(request.user):
            raise PermissionDenied()
        ev = self.get_object()
        if request.method == "POST":
            s = QuestionFullSerializer(data={**request.data, "evaluation": ev.id})
            s.is_valid(raise_exception=True)
            s.save()
            return Response(s.data, status=201)
        return Response(QuestionFullSerializer(ev.questions.all(), many=True).data)

    @action(detail=True, methods=["post"])
    def demarrer(self, request, pk=None):
        ev = self.get_object()
        now = timezone.now()
        if not (ev.debut <= now <= ev.fin):
            raise ValidationError("L'épreuve n'est pas ouverte actuellement.")
        done = ev.copies.filter(etudiant=request.user)
        enc = done.filter(statut="EN_COURS").first()
        if not enc:
            if done.count() >= ev.tentatives_max:
                raise ValidationError("Nombre maximal de tentatives atteint.")
            enc = Copie.objects.create(evaluation=ev, etudiant=request.user, tentative=done.count() + 1)
        qs = list(ev.questions.all())
        if ev.melanger_questions:
            random.Random(f"{enc.id}").shuffle(qs)  # ordre stable par copie
        deadline = min(enc.debut + timedelta(minutes=ev.duree_min), ev.fin)
        return Response({"copie": enc.id, "reponses": enc.reponses, "fin": deadline,
                         "questions": QuestionStudentSerializer(qs, many=True).data})

    def _copie(self, request, pk):
        c = Copie.objects.filter(pk=request.data.get("copie"), evaluation_id=pk, etudiant=request.user).first()
        if not c:
            raise ValidationError("Copie introuvable.")
        return c

    def _expired(self, c):
        return timezone.now() > min(c.debut + timedelta(minutes=c.evaluation.duree_min), c.evaluation.fin) + timedelta(seconds=30)

    @action(detail=True, methods=["post"])
    def repondre(self, request, pk=None):
        """Sauvegarde automatique des réponses."""
        c = self._copie(request, pk)
        if c.statut != "EN_COURS":
            raise ValidationError("Copie déjà soumise.")
        if self._expired(c):
            return self.soumettre(request, pk)
        c.reponses = {**c.reponses, **(request.data.get("reponses") or {})}
        c.save(update_fields=["reponses"])
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        c = self._copie(request, pk)
        if c.statut == "EN_COURS":
            c.reponses = {**c.reponses, **(request.data.get("reponses") or {})}
            c.soumise_le, c.statut = timezone.now(), Copie.Statut.SOUMISE
            grade_copy(c)
            c.save()
        show = c.evaluation.resultats_publies
        return Response({"statut": c.statut, "note": float(c.note_finale) if show and c.note_finale is not None else None})

    @action(detail=True, methods=["post"])
    def journal(self, request, pk=None):
        c = self._copie(request, pk)
        c.evenements = (c.evenements + [{"t": timezone.now().isoformat(), "e": str(request.data.get("evenement", ""))[:60]}])[-200:]
        c.save(update_fields=["evenements"])
        return Response({"ok": True})

    @action(detail=True, methods=["get"])
    def copies(self, request, pk=None):
        if not is_staff_like(request.user):
            raise PermissionDenied()
        ev = self.get_object()
        rows = ev.copies.select_related("etudiant").values("id", "etudiant__first_name", "etudiant__last_name", "statut", "note_auto", "note_finale", "soumise_le", "tentative")
        return Response(list(rows))

    @action(detail=True, methods=["post"], url_path="corriger/(?P<cid>[0-9]+)")
    def corriger(self, request, pk=None, cid=None):
        """Correction manuelle des questions ouvertes + validation de la note finale par l'enseignant."""
        if not is_staff_like(request.user):
            raise PermissionDenied()
        c = Copie.objects.get(pk=cid, evaluation_id=pk)
        manual = request.data.get("points") or {}
        c.detail_notes = {**c.detail_notes, **{str(k): float(v) for k, v in manual.items()}}
        c.note_finale = Decimal(str(sum(c.detail_notes.values())))
        c.commentaire, c.statut = request.data.get("commentaire", ""), Copie.Statut.CORRIGEE
        c.save()
        return Response({"note_finale": float(c.note_finale)})

    @action(detail=True, methods=["post"])
    def publier_resultats(self, request, pk=None):
        if not is_staff_like(request.user):
            raise PermissionDenied()
        ev = self.get_object()
        ev.resultats_publies = True
        ev.save()
        return Response({"ok": True})


# ───────────────────────── Notes ─────────────────────────
class NoteSerializer(serializers.ModelSerializer):
    ecue_code = serializers.CharField(source="ecue.code", read_only=True)
    ecue_intitule = serializers.CharField(source="ecue.intitule", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.full_name", read_only=True)

    class Meta:
        model = Note
        fields = "__all__"
        read_only_fields = ["saisie_par"]


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    filterset_fields = ["ecue", "annee", "type", "publiee", "etudiant"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrBackOffice()]

    def get_queryset(self):
        u = self.request.user
        qs = Note.objects.select_related("ecue", "etudiant")
        if u.role == "ENSEIGNANT":
            return qs.filter(ecue__enseignant=u)
        return qs if u.is_back_office else qs.filter(etudiant=u, publiee=True)  # notes officielles : après validation uniquement

    def create(self, request, *args, **kwargs):
        """Saisie idempotente : une note par (étudiant, ECUE, année, type). Une note déjà publiée n'est pas écrasée."""
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=False)
        d = {k: request.data.get(k) for k in ("etudiant", "ecue", "annee", "type")}
        if request.user.role == "ENSEIGNANT" and not request.user.ecues.filter(pk=d["ecue"]).exists():
            raise PermissionDenied("Vous n'êtes pas responsable de cette ECUE.")
        try:
            v = Decimal(str(request.data.get("valeur")))
        except Exception:
            raise ValidationError("Note invalide.")
        if not Decimal(0) <= v <= Decimal(20):
            raise ValidationError("La note doit être comprise entre 0 et 20.")
        existing = Note.objects.filter(etudiant_id=d["etudiant"], ecue_id=d["ecue"], annee_id=d["annee"], type=d["type"] or "EXAMEN").first()
        if existing and existing.publiee and not request.user.is_back_office:
            raise ValidationError("Note déjà publiée : seule la scolarité peut la modifier.")
        note, _ = Note.objects.update_or_create(
            etudiant_id=d["etudiant"], ecue_id=d["ecue"], annee_id=d["annee"], type=d["type"] or "EXAMEN",
            defaults={"valeur": v, "saisie_par": request.user})
        return Response(NoteSerializer(note).data, status=201)

    @action(detail=False, methods=["post"], permission_classes=[IsTeacherOrBackOffice])
    def publier(self, request):
        n = Note.objects.filter(ecue=request.data.get("ecue"), annee=request.data.get("annee")).update(publiee=True)
        return Response({"publiees": n})
