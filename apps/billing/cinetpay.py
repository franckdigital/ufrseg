"""Client CinetPay (API v1 « Aurora »), SANDBOX par défaut — repris du projet ae-akwaba-treich.

Flux : POST /v1/oauth/login {api_key, api_password} -> access_token ; POST /v1/payment -> payment_url ;
GET /v1/payment/{merchant_transaction_id} -> statut (SUCCESS / FAILED / INITIATED / PENDING / INSUFFICIENT_BALANCE).
Sandbox : https://api.cinetpay.net . Une clé « sk_live_ » est REFUSÉE sauf CINETPAY_ALLOW_LIVE=1.

Le statut d'un paiement n'est jamais pris sur parole (retour navigateur ou webhook) : il est toujours re-vérifié
auprès de CinetPay côté serveur avant d'activer un abonnement / soumettre un dossier.
"""
import logging
import re
import uuid

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("ufrseg.cinetpay")

SANDBOX_URL = "https://api.cinetpay.net"
LIVE_URL = "https://api.cinetpay.co"


class PaymentError(Exception):
    pass


class InitResult:
    def __init__(self, reference, redirect_url, raw=None, mock=False):
        self.reference, self.redirect_url, self.raw, self.mock = reference, redirect_url, raw or {}, mock


def new_reference(prefix="UFR"):
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def normalize_ci_phone(phone):
    """+225 + numéro local à 10 chiffres (le 0 initial est conservé), format attendu par CinetPay v1."""
    digits = re.sub(r"\D", "", phone or "")
    local = digits[3:] if digits.startswith("225") else digits
    if len(local) == 9 and not local.startswith("0"):
        local = "0" + local
    return f"+225{local}"


def is_mock():
    """Simulation locale : jamais en production (DEBUG requis)."""
    return bool(settings.CINETPAY_MOCK) and bool(settings.DEBUG)


def _base_url():
    key = settings.CINETPAY_API_KEY
    if key.startswith("sk_live_"):
        if not settings.CINETPAY_ALLOW_LIVE:
            raise PaymentError("Clé CinetPay LIVE détectée : ce projet est configuré pour le SANDBOX. "
                               "Utilisez une clé sk_test_ (ou définissez CINETPAY_ALLOW_LIVE=1 en connaissance de cause).")
        return LIVE_URL
    return SANDBOX_URL


def _token():
    if not settings.CINETPAY_API_KEY or not settings.CINETPAY_API_PASSWORD:
        raise PaymentError("CinetPay non configuré : renseignez CINETPAY_API_KEY et CINETPAY_API_PASSWORD dans backend/.env.")
    token = cache.get("ufrseg_cinetpay_token")
    if token:
        return token
    try:
        r = requests.post(f"{_base_url()}/v1/oauth/login", json={"api_key": settings.CINETPAY_API_KEY,
                                                                   "api_password": settings.CINETPAY_API_PASSWORD}, timeout=30)
        data = r.json()
    except requests.exceptions.RequestException as e:
        raise PaymentError(f"CinetPay : erreur réseau ({e})")
    except ValueError:
        raise PaymentError("CinetPay : réponse invalide à l'authentification")
    if data.get("code") != 200 or not data.get("access_token"):
        raise PaymentError(data.get("description") or data.get("status") or "Authentification CinetPay échouée")
    token = data["access_token"]
    cache.set("ufrseg_cinetpay_token", token, min(max(int(data.get("expires_in", 240)) - 30, 60), 240))
    return token


def init_payment(payment, designation):
    """Démarre le paiement hébergé CinetPay pour un `billing.Payment`. -> InitResult(reference, redirect_url)."""
    user = payment.user
    ref = new_reference()
    base = settings.PUBLIC_WEB_URL.rstrip("/")
    back = f"{base}/paiement/retour?ref={payment.reference}"
    if is_mock():
        logger.warning("CinetPay MOCK — pas d'appel réseau")
        return InitResult(ref, None, {"mock": True}, mock=True)

    token = _token()
    phone = normalize_ci_phone(payment.payer_phone or user.phone)
    if len(phone) != 14:
        raise PaymentError("Numéro de téléphone invalide : saisissez un mobile ivoirien à 10 chiffres (ex. 0707123456).")
    payload = {
        "currency": "XOF", "merchant_transaction_id": ref, "amount": int(payment.montant), "lang": "fr",
        "designation": designation[:120],
        "client_email": user.email or f"{phone.replace('+', '')}@noemail.ufrseg.ci",
        "client_phone_number": phone,
        "client_first_name": (user.first_name or "Etudiant")[:255], "client_last_name": (user.last_name or "UFR SEG")[:255],
        "direct_pay": False, "success_url": back, "failed_url": back,
        "notify_url": f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/billing/cinetpay-webhook/",
    }
    try:
        r = requests.post(f"{_base_url()}/v1/payment", json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        logger.info("CinetPay HTTP %s %.400s", r.status_code, r.text)
        data = r.json()
    except requests.exceptions.Timeout:
        raise PaymentError("CinetPay : délai d'attente dépassé")
    except requests.exceptions.RequestException as e:
        raise PaymentError(f"CinetPay : erreur réseau ({e})")
    except ValueError:
        raise PaymentError("CinetPay : réponse invalide (non-JSON)")
    if data.get("code") != 200 or not data.get("payment_url"):
        details = data.get("details") or {}
        errors = details.get("errors")
        msg = "; ".join(f"{k}: {v}" for k, v in errors.items()) if errors else (
            details.get("message") or data.get("description") or data.get("message") or "Erreur CinetPay")
        raise PaymentError(f"CinetPay : {msg} (code={data.get('code')})")
    return InitResult(ref, data["payment_url"], data)


def verify_payment(reference):
    """Interroge CinetPay. -> ("succeeded" | "failed" | "pending", raw)."""
    if is_mock():
        return "pending", {"mock": True}
    try:
        r = requests.get(f"{_base_url()}/v1/payment/{reference}", headers={"Authorization": f"Bearer {_token()}"}, timeout=20)
        data = r.json()
    except requests.exceptions.RequestException as e:
        raise PaymentError(f"CinetPay : erreur réseau ({e})")
    except ValueError:
        raise PaymentError("CinetPay : réponse invalide (non-JSON)")
    status = (data.get("status") or "").upper()
    if status == "SUCCESS":
        return "succeeded", data
    if status in ("FAILED", "INSUFFICIENT_BALANCE", "EXPIRED", "CANCELED", "CANCELLED"):
        return "failed", data
    return "pending", data
