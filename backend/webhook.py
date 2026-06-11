"""Webhooks SendGrid — porté du scraper de base (src/webhook/server.py).

- Inbound Parse  : réception des réponses email → classement automatique
  (repondu / interesse / desabonne via mots-clés STOP…) + mise à jour du
  prospect + transfert de la réponse vers la boîte de l'expéditeur.
- Event Webhook  : bounces / spam / désabonnements → opt-out ou email invalide.

Sécurité : token secret dans l'URL (?token=…), généré au démarrage.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from autopilot import send_email_sync
from scraper_core import as_str

logger = logging.getLogger("webhook")

# Mots-clés (portés du scraper de base, avec limites de mots pour éviter les faux positifs)
STOP_RE = re.compile(r"\b(stop|d[ée]sabonn\w*|ne plus|pas int[ée]ress|plus de mail|spam)\b", re.I)
INTERESSE_RE = re.compile(r"\b(oui|int[ée]ress[ée]?s?|rappeler|rappelez|rendez-vous|rdv|devis)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_reply(text: str) -> str:
    """repondu | interesse | desabonne — même logique que le scraper de base."""
    if STOP_RE.search(text):
        return "desabonne"
    if INTERESSE_RE.search(text):
        return "interesse"
    return "repondu"


def _email_query(email: str) -> dict:
    return {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}


def create_router(db) -> APIRouter:
    router = APIRouter(prefix="/webhook")

    async def get_settings_checked(token: str) -> dict:
        s = await db.settings.find_one({"_id": "global"}) or {}
        expected = as_str(s.get("webhook_token"))
        if expected and token != expected:
            raise HTTPException(401, "Token webhook invalide")
        return s

    @router.post("/sendgrid/inbound")
    async def inbound_parse(request: Request, token: str = ""):
        """Réception d'une réponse email (SendGrid Inbound Parse, multipart/form-data)."""
        settings = await get_settings_checked(token)
        form = await request.form()
        from_field = str(form.get("from", ""))
        subject = str(form.get("subject", ""))
        text = str(form.get("text", "") or form.get("html", ""))

        m = EMAIL_RE.search(from_field)
        email_from = m.group(0).lower() if m else ""
        action = classify_reply(f"{subject}\n{text}")

        reponse = {
            "id": str(uuid.uuid4()), "de": email_from, "de_complet": from_field[:200],
            "objet": subject[:300], "texte": text[:2000], "action": action,
            "prospect_id": None, "entreprise": "", "date": now_iso(),
        }

        p = await db.prospects.find_one(_email_query(email_from), {"_id": 0}) if email_from else None
        if p:
            reponse["prospect_id"] = p["id"]
            reponse["entreprise"] = as_str(p.get("entreprise"))
            nouveau_statut = "opt_out" if action == "desabonne" else "repondu"
            await db.prospects.update_one(
                {"id": p["id"]},
                {"$set": {"statut": nouveau_statut, "reply_action": action},
                 "$push": {"historique": {
                     "type": "reponse_email", "action": action, "date": now_iso(),
                     "objet": subject[:200], "extrait": text[:300]}}})
            logger.info(f"Webhook : réponse de {email_from} ({p.get('entreprise')}) → {action}")
        else:
            logger.info(f"Webhook : réponse de {email_from} — aucun prospect correspondant")

        await db.reponses.insert_one({**reponse})

        # Transfert de la réponse vers la boîte de l'expéditeur (pour la lire dans sa messagerie)
        key = as_str(settings.get("sendgrid_api_key"))
        sender = as_str(settings.get("email_expediteur"))
        if key and sender and email_from != sender.lower():
            corps = (f"De : {from_field}\nAction détectée : {action}"
                     f"{' — prospect : ' + reponse['entreprise'] if p else ' — prospect inconnu'}"
                     f"\n\n--- Message ---\n{text[:3000]}")
            try:
                await asyncio.to_thread(
                    send_email_sync, key, sender, "Cockpit Prospection",
                    sender, f"[Réponse prospect] {subject or '(sans objet)'}", corps)
            except Exception as e:
                logger.warning(f"Webhook : transfert de la réponse impossible : {e}")

        return {"ok": True, "action": action, "prospect_trouve": bool(p)}

    @router.post("/sendgrid/events")
    async def event_webhook(request: Request, token: str = ""):
        """Événements SendGrid : bounce/dropped → email invalide ; spam/désabo → opt-out."""
        await get_settings_checked(token)
        try:
            events = await request.json()
        except Exception:
            events = []
        traites = 0
        for ev in events if isinstance(events, list) else []:
            email = str(ev.get("email", "")).lower().strip()
            typ = str(ev.get("event", ""))
            if not email or not typ:
                continue
            await db.email_events.insert_one({
                "id": str(uuid.uuid4()), "email": email, "event": typ,
                "raison": str(ev.get("reason", ""))[:300], "date": now_iso()})
            if typ in ("unsubscribe", "group_unsubscribe", "spamreport"):
                await db.prospects.update_one(
                    _email_query(email),
                    {"$set": {"statut": "opt_out"},
                     "$push": {"historique": {"type": "desabonnement", "via": typ, "date": now_iso()}}})
            elif typ in ("bounce", "dropped"):
                await db.prospects.update_one(
                    _email_query(email),
                    {"$set": {"email_invalide": True},
                     "$push": {"historique": {"type": "email_invalide", "via": typ,
                                              "raison": str(ev.get("reason", ""))[:200], "date": now_iso()}}})
            traites += 1
        return {"ok": True, "traites": traites}

    @router.get("/reponses")
    async def list_reponses(limit: int = 50):
        items = await db.reponses.find({}, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
        return {"items": items}

    return router
