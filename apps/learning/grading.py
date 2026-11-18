"""Correction automatique des questions compatibles (QCM, multi, V/F, trous, numérique)."""
from decimal import Decimal

AUTO_TYPES = {"QCM", "MULTI", "VF", "TROUS", "NUM"}


def _norm(s):
    return " ".join(str(s).strip().lower().split())


def grade_question(q, answer):
    """Retourne les points obtenus, ou None si la question exige une correction manuelle."""
    if q.type not in AUTO_TYPES:
        return None
    if answer in (None, "", []):
        return Decimal(0)
    ok = False
    exp = q.reponse
    try:
        if q.type == "QCM":
            ok = int(answer) == int(exp)
        elif q.type == "MULTI":
            ok = set(map(int, answer)) == set(map(int, exp))
        elif q.type == "VF":
            ok = (str(answer).lower() in ("true", "vrai", "1")) == bool(exp)
        elif q.type == "TROUS":
            ok = _norm(answer) in {_norm(x) for x in (exp if isinstance(exp, list) else [exp])}
        elif q.type == "NUM":
            tol = float(exp.get("tolerance", 0))
            ok = abs(float(str(answer).replace(",", ".")) - float(exp["valeur"])) <= tol
    except (ValueError, TypeError, KeyError):
        ok = False
    return q.bareme if ok else Decimal(0)


def grade_copy(copie):
    questions = list(copie.evaluation.questions.all())
    detail, auto, manual_pending = {}, Decimal(0), False
    for q in questions:
        pts = grade_question(q, copie.reponses.get(str(q.id)))
        if pts is None:
            manual_pending = True
        else:
            detail[str(q.id)] = float(pts)
            auto += pts
    copie.detail_notes = {**copie.detail_notes, **{k: v for k, v in detail.items()}}
    copie.note_auto = auto
    if not manual_pending:
        copie.note_finale = auto
        copie.statut = copie.Statut.CORRIGEE
    return copie
