"""Agent IA de la vitrine : répond sur l'UFR à partir de la FAQ, des formations et des tarifs.
Utilise l'API Claude si ANTHROPIC_API_KEY est défini, sinon un moteur local par mots-clés (aucun coût)."""
import re
import unicodedata

from django.conf import settings

SYSTEM = (
    "Tu es l'assistant virtuel de l'UFR des Sciences Économiques et de Gestion (SEG) de l'Université Félix "
    "Houphouët-Boigny (Abidjan). Réponds en français, de façon courte, claire et chaleureuse. "
    "Appuie-toi UNIQUEMENT sur le contexte fourni ; si l'information n'y figure pas, invite à contacter la "
    "scolarité ou le décanat. Tu n'annonces jamais de résultats, validations ou décisions officielles."
)


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


STOP = set("le la les un une des de du et en a au aux je tu il que qui quoi est ce se sur pour par dans comment quel quelle quels quelles mon ma mes ou y".split())


def build_context():
    from apps.academics.models import Filiere
    from apps.billing.models import Plan
    from .models import FAQ

    parts = ["FAQ :"]
    parts += [f"- Q: {f.question}\n  R: {f.reponse}" for f in FAQ.objects.all()[:40]]
    parts.append("Formations : " + "; ".join(f"{f.nom} ({f.code})" for f in Filiere.objects.all()))
    parts.append("Abonnements bibliothèque (FCFA) : " + "; ".join(f"{p.get_pack_display()} {p.mois} mois = {p.prix}" for p in Plan.objects.filter(actif=True)))
    return "\n".join(parts)


def local_answer(question):
    from .models import FAQ

    q = {w for w in _norm(question).split() if w not in STOP and len(w) > 2}
    best, score = None, 0
    for f in FAQ.objects.all():
        words = {w for w in _norm(f.question + " " + f.reponse).split() if w not in STOP}
        s = len(q & words)
        if s > score:
            best, score = f, s
    if best and score >= 1:
        return best.reponse
    return ("Je n'ai pas trouvé d'information précise sur ce point. Contactez le service de scolarité ou le décanat "
            "via la page Contact, ou prenez rendez-vous depuis votre espace étudiant.")


def ask(question, history=None):
    question = question.strip()[:600]
    if not settings.ANTHROPIC_API_KEY:
        return local_answer(question), "local"
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msgs = [{"role": m["role"], "content": m["content"][:600]} for m in (history or [])[-6:] if m.get("role") in ("user", "assistant")]
        msgs.append({"role": "user", "content": question})
        r = client.messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=400, system=SYSTEM + "\n\nCONTEXTE:\n" + build_context(), messages=msgs)
        return r.content[0].text, "claude"
    except Exception:
        return local_answer(question), "local"
