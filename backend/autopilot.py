"""Pilote automatique d'envoi d'emails — porté du campaign_manager du scraper de base.

Boucle de fond : toutes les 5 minutes, envoie automatiquement les emails des
prospects dus dont l'étape courante de séquence est de canal "email".
Respecte : quota journalier, plage horaire (Europe/Paris), jours ouvrés,
arrêt si répondu / opt-out (géré par le statut du pipeline).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from prospection import DEFAULT_SCENARIOS, advance_updates, render_message
from scraper_core import as_str

logger = logging.getLogger("autopilot")

PARIS = ZoneInfo("Europe/Paris")
TICK_SECONDS = 300  # vérification toutes les 5 minutes

DEFAULT_OBJET = "Votre présence en ligne — {entreprise}"
FOOTER = "\n\n—\nSi vous ne souhaitez plus recevoir mes messages, répondez simplement STOP."


def send_email_sync(api_key: str, sender: str, sender_name: str, to: str, subject: str, body: str) -> int:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    html = body.replace("\n", "<br>")
    from_email = (sender, sender_name) if sender_name else sender
    message = Mail(from_email=from_email, to_emails=to, subject=subject, html_content=html)
    sg = SendGridAPIClient(api_key)
    resp = sg.send(message)
    return resp.status_code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_start_paris_iso() -> str:
    """Début de la journée (heure de Paris), converti en ISO UTC."""
    start = datetime.now(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat()


def in_window(settings: dict) -> tuple[bool, str]:
    """La plage d'envoi est-elle ouverte ? (heure de Paris)"""
    now = datetime.now(PARIS)
    if settings.get("autopilot_jours_ouvres", True) and now.weekday() >= 5:
        return False, "Week-end — envois en jours ouvrés uniquement"
    debut = int(settings.get("autopilot_heure_debut", 9) or 0)
    fin = int(settings.get("autopilot_heure_fin", 18) or 24)
    if not (debut <= now.hour < fin):
        return False, f"Hors plage horaire {debut}h–{fin}h (il est {now.hour}h{now.minute:02d} à Paris)"
    return True, ""


async def get_scenario(db, profil: str) -> dict:
    sc = await db.scenarios.find_one({"profil": profil}, {"_id": 0})
    return sc or DEFAULT_SCENARIOS.get(profil, DEFAULT_SCENARIOS["site_moyen"])


async def count_sent_today(db) -> int:
    return await db.email_log.count_documents(
        {"statut": "envoye", "date": {"$gte": today_start_paris_iso()}})


async def eligible_prospects(db) -> list[tuple[dict, dict, list]]:
    """Prospects dus dont l'étape courante est un email et qui ont une adresse."""
    out = []
    cursor = db.prospects.find(
        {"statut": "a_contacter", "date_prochaine_action": {"$lte": now_iso()},
         "email": {"$exists": True, "$nin": ["", None]}},
        {"_id": 0},
    ).sort("score_conversion", -1)
    async for p in cursor:
        scenario = await get_scenario(db, p.get("profil", "site_moyen"))
        etapes = scenario.get("etapes", [])
        if not etapes:
            continue
        idx = min(max(int(p.get("etape_relance", 1)) - 1, 0), len(etapes) - 1)
        step = etapes[idx]
        if step.get("canal") != "email":
            continue
        out.append((p, step, etapes))
    return out


async def run_tick(db, force: bool = False) -> dict:
    """Un passage du pilote : envoie les emails dus, dans la limite du quota.

    force=True (déclenchement manuel) ignore l'interrupteur et la plage horaire,
    mais respecte le quota journalier.
    """
    settings = await db.settings.find_one({"_id": "global"}) or {}
    if not force and not settings.get("autopilot_actif"):
        return {"executed": False, "raison": "Pilote automatique désactivé"}
    key = as_str(settings.get("sendgrid_api_key"))
    sender = as_str(settings.get("email_expediteur"))
    if not key or not sender:
        return {"executed": False, "raison": "SendGrid non configuré (clé ou email expéditeur manquant)"}
    if not force:
        ok, raison = in_window(settings)
        if not ok:
            return {"executed": False, "raison": raison}

    quota = int(settings.get("autopilot_quota_jour", 50) or 50)
    deja = await count_sent_today(db)
    restant = quota - deja
    if restant <= 0:
        return {"executed": False, "raison": f"Quota journalier atteint ({deja}/{quota})"}

    candidats = await eligible_prospects(db)
    prenom = as_str(settings.get("prenom_expediteur"))
    envoyes, erreurs = 0, 0

    for p, step, etapes in candidats[:restant]:
        message = as_str(p.get("message_personnalise")) or render_message(step.get("template", ""), p, settings)
        objet = render_message(as_str(step.get("objet")) or DEFAULT_OBJET, p, settings)
        entry = {
            "id": str(uuid.uuid4()), "prospect_id": p["id"],
            "entreprise": as_str(p.get("entreprise")), "destinataire": p["email"],
            "objet": objet, "etape": int(p.get("etape_relance", 1)),
            "auto": True, "date": now_iso(),
        }
        try:
            status = await asyncio.to_thread(
                send_email_sync, key, sender, prenom, p["email"], objet, message + FOOTER)
            if status not in (200, 201, 202):
                raise RuntimeError(f"SendGrid a répondu {status}")
            entry["statut"] = "envoye"
            await db.prospects.update_one(
                {"id": p["id"]},
                {"$set": advance_updates(p, etapes),
                 "$push": {"historique": {
                     "type": "envoye", "canal": "email", "auto": True,
                     "date": now_iso(), "etape": int(p.get("etape_relance", 1)),
                     "objet": objet}}})
            envoyes += 1
        except Exception as e:
            logger.warning(f"Autopilot : échec envoi à {p['email']} : {e}")
            entry["statut"] = "erreur"
            entry["erreur"] = str(e)[:300]
            erreurs += 1
        await db.email_log.insert_one(entry)

    return {"executed": True, "envoyes": envoyes, "erreurs": erreurs,
            "candidats": len(candidats), "quota_restant": restant - envoyes}


async def autopilot_loop(db):
    """Boucle de fond du pilote automatique."""
    await asyncio.sleep(10)
    while True:
        try:
            res = await run_tick(db)
            if res.get("executed") and (res.get("envoyes") or res.get("erreurs")):
                logger.info(f"Autopilot : {res}")
        except Exception:
            logger.exception("Autopilot : erreur de boucle")
        await asyncio.sleep(TICK_SECONDS)
