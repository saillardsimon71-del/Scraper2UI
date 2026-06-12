"""API Cockpit de Prospection — scraper + file du jour + séquences."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from prospection import (
    DEFAULT_SCENARIOS, PROFIL_LABELS, PROFILS, STATUT_LABELS,
    accroche_saison, advance_updates, canal_plan, determine_canal, determine_profil,
    pick_objet, render_message, step_template,
)
from scraper_core import (
    METIERS, USER_AGENT, as_str, audit_site, build_linkedin_link, build_wa_link,
    compute_score, compute_site_vendabilite, discover_gouv, discover_osm, enrich_email, enrich_phone,
    has_real_website, niveau_from_score, normalize_company_name,
    normalize_french_phone, phone_digits, resolve_site_web, serper_find_site,
)
from autopilot import (
    autopilot_loop, count_sent_today, eligible_prospects, in_window,
    run_tick, send_email_sync,
)
from backup import (
    backup_loop, backup_status, dump_db, restore_db, restore_if_empty,
)
from sendgrid_import import (
    aggregate_by_recipient, fetch_sent_messages, _entreprise_from_email_or_subject,
    _extract_site_from_subject,
)
from inbox import (
    classify, fetch_recent_messages, test_connection as test_imap_connection,
)
from replies_recovery import (
    fetch_notifications, fetch_outgoing, match_notifications_to_outgoing,
)
from webhook import create_router as create_webhook_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Cockpit Prospection")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_start_iso() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# ============================================================ Modèles

class ScrapeRequest(BaseModel):
    metiers: list[str]
    villes: list[str]
    departement: str = ""
    limite: int = 20  # par combinaison métier × ville
    source: str = "gouv"  # gouv | osm
    auditer: bool = True


class ActionRequest(BaseModel):
    type: str  # envoye | repondu | rdv | skip | opt_out | perdu | gagne | reactiver | rappel
    raison_refus: Optional[str] = None  # pour action perdu/opt_out
    ca_contrat: Optional[float] = None  # pour action gagne (montant en €)
    rappel_dans_jours: Optional[int] = None  # pour action rappel (1-90 jours)


class ProspectUpdate(BaseModel):
    telephone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    site_web: Optional[str] = None
    notes: Optional[str] = None
    statut: Optional[str] = None
    message_personnalise: Optional[str] = None
    profil: Optional[str] = None
    ca_contrat: Optional[float] = None
    raison_refus: Optional[str] = None


class AIImproveRequest(BaseModel):
    message: str
    prospect_id: Optional[str] = None
    canal: str = "whatsapp"
    instruction: str = ""


class SettingsUpdate(BaseModel):
    prenom_expediteur: Optional[str] = None
    lien_rdv: Optional[str] = None
    offre: Optional[str] = None
    serper_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    email_expediteur: Optional[str] = None
    email_reponse: Optional[str] = None
    autopilot_actif: Optional[bool] = None
    autopilot_quota_jour: Optional[int] = None
    autopilot_heure_debut: Optional[int] = None
    autopilot_heure_fin: Optional[int] = None
    autopilot_jours_ouvres: Optional[bool] = None
    # IMAP : lecture des réponses reçues dans la boîte mail
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_folder: Optional[str] = None


class EtapeModel(BaseModel):
    etape: int
    delai_jours: int
    template: str
    objet: str = ""
    objet_b: str = ""  # variante B de l'objet (A/B testing email)
    template_court: str = ""  # variante 2-3 lignes pour WhatsApp / LinkedIn


class MiniAuditRequest(BaseModel):
    prospect_id: str


class EmailSendRequest(BaseModel):
    prospect_id: str
    subject: str
    message: str


class ScenarioUpdate(BaseModel):
    etapes: list[EtapeModel]


# ============================================================ Helpers

async def get_settings() -> dict:
    s = await db.settings.find_one({"_id": "global"}) or {}
    s.pop("_id", None)
    return s


async def get_scenario(profil: str) -> dict:
    sc = await db.scenarios.find_one({"profil": profil}, {"_id": 0})
    return sc or DEFAULT_SCENARIOS.get(profil, DEFAULT_SCENARIOS["site_moyen"])


def prepare_new_prospect(data: dict) -> dict:
    """Complète un prospect brut : score, profil, statut, file d'attente."""
    p = {
        "id": str(uuid.uuid4()),
        "entreprise": as_str(data.get("entreprise")),
        "nom": as_str(data.get("nom")),
        "metier": as_str(data.get("metier")),
        "ville": as_str(data.get("ville")),
        "code_postal": as_str(data.get("code_postal")),
        "adresse": as_str(data.get("adresse")),
        "siren": as_str(data.get("siren")),
        "telephone": normalize_french_phone(data.get("telephone", "")),
        "email": as_str(data.get("email")),
        "site_web": as_str(data.get("site_web")),
        "linkedin_url": as_str(data.get("linkedin_url")),
        "note_site": int(data.get("note_site", 0) or 0),
        "qualite_site": as_str(data.get("qualite_site")),
        "opportunites": as_str(data.get("opportunites")),
        "signaux_conversion": as_str(data.get("signaux_conversion")),
        "signal_principal": as_str(data.get("signal_principal")),
        "score_conversion": int(data.get("score_conversion", 0) or 0),
        "niveau_conversion": as_str(data.get("niveau_conversion")),
        "message_whatsapp": as_str(data.get("message_whatsapp")),
        "message_linkedin": as_str(data.get("message_linkedin")),
        "message_personnalise": "",
        "source": as_str(data.get("source")) or "import",
        "statut": "a_contacter",
        "etape_relance": 1,
        "date_prochaine_action": now_iso(),
        "notes": "",
        "historique": [],
        "created_at": now_iso(),
        "ca_contrat": None,
        "raison_refus": "",
        "date_rappel": None,
    }
    if not p["score_conversion"]:
        p["score_conversion"], p["niveau_conversion"] = compute_score(p)
    if not p["niveau_conversion"]:
        p["niveau_conversion"] = niveau_from_score(p["score_conversion"])
    p["profil"] = as_str(data.get("profil")) or determine_profil(p)
    n_etapes = len(DEFAULT_SCENARIOS.get(p["profil"], DEFAULT_SCENARIOS["site_moyen"])["etapes"])
    plan = canal_plan(p, n_etapes)
    p["plan_canaux"] = plan
    p["canal_contact"] = plan[0] if plan else ""
    p["variante_ab"] = random.choice(["A", "B"])  # A/B testing des objets d'email
    p["entreprise_norm"] = normalize_company_name(p["entreprise"])
    p["tel_digits"] = phone_digits(p["telephone"])
    # Vendabilité du site (argumentaire commercial)
    vendabilite = compute_site_vendabilite(p)
    p.update(vendabilite)
    return p


async def find_duplicate(p: dict) -> Optional[dict]:
    ors = []
    if p.get("siren"):
        ors.append({"siren": p["siren"]})
    if p.get("tel_digits"):
        ors.append({"tel_digits": p["tel_digits"]})
    if p.get("entreprise_norm"):
        ors.append({"entreprise_norm": p["entreprise_norm"], "ville": p.get("ville", "")})
    if not ors:
        return None
    return await db.prospects.find_one({"$or": ors}, {"_id": 0, "id": 1})


async def build_queue_item(p: dict, settings: dict) -> dict:
    scenario = await get_scenario(p.get("profil", "site_moyen"))
    etapes = scenario.get("etapes", [])
    idx = min(max(int(p.get("etape_relance", 1)) - 1, 0), len(etapes) - 1) if etapes else 0
    step = etapes[idx] if etapes else {"etape": 1, "template": "", "delai_jours": 0}
    canal = p.get("canal_contact") or determine_canal(p) or "whatsapp"
    message = as_str(p.get("message_personnalise")) or render_message(step_template(step, canal), p, settings)
    return {
        "prospect": p,
        "etape": step.get("etape", 1),
        "total_etapes": len(etapes),
        "canal": canal,
        "message": message,
        "accroche_saison": accroche_saison(as_str(p.get("metier"))),
        "wa_link": build_wa_link(p.get("telephone", ""), message),
        "linkedin_link": build_linkedin_link(p.get("linkedin_url", ""), p.get("entreprise", ""), p.get("ville", "")),
    }


# ============================================================ Dashboard / File du jour

@api_router.get("/")
async def root():
    return {"message": "Cockpit Prospection API"}


@api_router.get("/dashboard/stats")
async def dashboard_stats():
    total = await db.prospects.count_documents({})
    file_du_jour = await db.prospects.count_documents(
        {"statut": "a_contacter", "date_prochaine_action": {"$lte": now_iso()},
         "canal_contact": {"$in": ["whatsapp", "linkedin", "telephone"]}})
    envoyes_auj = await db.prospects.count_documents(
        {"historique": {"$elemMatch": {"type": "envoye", "date": {"$gte": today_start_iso()}}}})
    repondus = await db.prospects.count_documents({"statut": {"$in": ["repondu", "rdv", "gagne"]}})
    contactes = await db.prospects.count_documents({"historique.type": "envoye"})
    taux = round(repondus / contactes * 100, 1) if contactes else 0.0

    par_statut = {}
    async for row in db.prospects.aggregate([{"$group": {"_id": "$statut", "n": {"$sum": 1}}}]):
        par_statut[row["_id"]] = row["n"]
    par_niveau = {}
    async for row in db.prospects.aggregate([{"$group": {"_id": "$niveau_conversion", "n": {"$sum": 1}}}]):
        par_niveau[row["_id"]] = row["n"]

    return {"total": total, "file_du_jour": file_du_jour, "envoyes_aujourdhui": envoyes_auj,
            "repondus": repondus, "contactes": contactes, "taux_reponse": taux,
            "par_statut": par_statut, "par_niveau": par_niveau}


@api_router.get("/dashboard/business")
async def dashboard_business():
    """Stats business : entonnoir de conversion, CA, raisons de refus."""
    total = await db.prospects.count_documents({})
    contactes = await db.prospects.count_documents({"historique.type": "envoye"})
    repondus = await db.prospects.count_documents({"statut": {"$in": ["repondu", "rdv", "gagne"]}})
    rdv = await db.prospects.count_documents({"statut": {"$in": ["rdv", "gagne"]}})
    gagnes = await db.prospects.count_documents({"statut": "gagne"})
    perdus = await db.prospects.count_documents({"statut": {"$in": ["perdu", "opt_out", "epuise"]}})

    # CA total et moyen
    ca_pipeline = [
        {"$match": {"statut": "gagne", "ca_contrat": {"$ne": None, "$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$ca_contrat"}, "count": {"$sum": 1},
                    "min": {"$min": "$ca_contrat"}, "max": {"$max": "$ca_contrat"}}},
    ]
    ca_res = await db.prospects.aggregate(ca_pipeline).to_list(1)
    ca_total = ca_res[0]["total"] if ca_res else 0
    ca_count = ca_res[0]["count"] if ca_res else 0
    ca_moyen = round(ca_total / ca_count, 0) if ca_count else 0

    # Raisons de refus (top 8)
    refus_pipeline = [
        {"$match": {"raison_refus": {"$nin": ["", None]}}},
        {"$group": {"_id": "$raison_refus", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 8},
    ]
    raisons_refus = [{"raison": r["_id"], "n": r["n"]}
                     async for r in db.prospects.aggregate(refus_pipeline)]

    # Taux de conversion par profil
    profil_pipeline = [
        {"$group": {"_id": "$profil",
                    "total": {"$sum": 1},
                    "gagnes": {"$sum": {"$cond": [{"$eq": ["$statut", "gagne"]}, 1, 0]}},
                    "repondus": {"$sum": {"$cond": [{"$in": ["$statut", ["repondu", "rdv", "gagne"]]}, 1, 0]}}}},
    ]
    par_profil = {}
    async for row in db.prospects.aggregate(profil_pipeline):
        if row["_id"]:
            par_profil[row["_id"]] = {
                "total": row["total"],
                "gagnes": row["gagnes"],
                "repondus": row["repondus"],
                "taux_reponse": round(row["repondus"] / row["total"] * 100, 1) if row["total"] else 0,
                "taux_conversion": round(row["gagnes"] / row["total"] * 100, 1) if row["total"] else 0,
            }

    # Derniers clients gagnés
    derniers_gagnes = await db.prospects.find(
        {"statut": "gagne"}, {"_id": 0, "entreprise": 1, "ville": 1, "metier": 1,
                               "ca_contrat": 1, "created_at": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    # Performance par canal / étape / objet d'email (A/B), à partir de l'historique.
    # Une réponse est créditée au dernier envoi qui la précède.
    SEND_TYPES = {"envoye", "email_envoye"}
    REPLY_TYPES = {"reponse_email", "repondu", "rdv", "gagne"}
    par_canal: dict[str, dict] = {}
    par_etape: dict[int, dict] = {}
    ab_objets = {"A": {"envois": 0, "reponses": 0}, "B": {"envois": 0, "reponses": 0}}
    objets: dict[tuple, dict] = {}

    async for p in db.prospects.find(
            {"historique.0": {"$exists": True}}, {"_id": 0, "historique": 1, "statut": 1}):
        hist = p.get("historique", []) or []
        sends = [h for h in hist if h.get("type") in SEND_TYPES]
        if not sends:
            continue
        reply_pos = next((i for i, h in enumerate(hist) if h.get("type") in REPLY_TYPES), None)
        responded = reply_pos is not None or p.get("statut") in ("repondu", "rdv", "gagne", "interesse")
        credited = None
        if responded:
            if reply_pos is not None:
                prior = [h for h in hist[:reply_pos] if h.get("type") in SEND_TYPES]
                credited = prior[-1] if prior else sends[0]
            else:
                credited = sends[-1]

        for h in sends:
            canal = h.get("canal") or ("email" if h.get("type") == "email_envoye" else "autre")
            try:
                etape = int(h.get("etape", 1) or 1)
            except (TypeError, ValueError):
                etape = 1
            is_credited = h is credited
            par_canal.setdefault(canal, {"envois": 0, "reponses": 0})["envois"] += 1
            par_etape.setdefault(etape, {"envois": 0, "reponses": 0})["envois"] += 1
            if is_credited:
                par_canal[canal]["reponses"] += 1
                par_etape[etape]["reponses"] += 1
            if canal == "email":
                variante = h.get("variante")
                if variante in ("A", "B"):
                    ab_objets[variante]["envois"] += 1
                    if is_credited:
                        ab_objets[variante]["reponses"] += 1
                objet_t = as_str(h.get("objet_template"))
                if objet_t:
                    key = (objet_t, variante or "")
                    o = objets.setdefault(key, {"objet": objet_t, "variante": variante or "",
                                                "envois": 0, "reponses": 0})
                    o["envois"] += 1
                    if is_credited:
                        o["reponses"] += 1

    def _rate(d: dict) -> dict:
        d["taux"] = round(d["reponses"] / d["envois"] * 100, 1) if d["envois"] else 0.0
        return d

    top_objets = sorted((_rate(o) for o in objets.values()),
                        key=lambda o: (-o["envois"], -o["taux"]))[:12]

    return {
        "entonnoir": {
            "total": total,
            "contactes": contactes,
            "repondus": repondus,
            "rdv": rdv,
            "gagnes": gagnes,
            "perdus": perdus,
        },
        "ca": {
            "total": ca_total,
            "moyen": ca_moyen,
            "count": ca_count,
        },
        "raisons_refus": raisons_refus,
        "par_profil": par_profil,
        "derniers_gagnes": derniers_gagnes,
        "taux_reponse": round(repondus / contactes * 100, 1) if contactes else 0,
        "taux_rdv": round(rdv / repondus * 100, 1) if repondus else 0,
        "taux_signature": round(gagnes / rdv * 100, 1) if rdv else 0,
        "par_canal": {c: _rate(v) for c, v in par_canal.items()},
        "par_etape": [{"etape": k, **_rate(v)} for k, v in sorted(par_etape.items())],
        "ab_objets": {k: _rate(v) for k, v in ab_objets.items()},
        "top_objets": top_objets,
    }


@api_router.get("/queue")
async def get_queue(limit: int = 50):
    """File du jour : actions manuelles uniquement (WhatsApp / LinkedIn / appel téléphone).

    Les prospects au canal email sont gérés par le pilote automatique.
    """
    settings = await get_settings()
    cursor = db.prospects.find(
        {"statut": "a_contacter", "date_prochaine_action": {"$lte": now_iso()},
         "canal_contact": {"$in": ["whatsapp", "linkedin", "telephone"]}},
        {"_id": 0},
    ).sort([("score_vendabilite", -1), ("score_conversion", -1), ("created_at", -1)]).limit(limit)
    items = []
    async for p in cursor:
        items.append(await build_queue_item(p, settings))
    return {"items": items, "count": len(items)}


# ============================================================ Prospects

@api_router.get("/prospects")
async def list_prospects(q: str = "", statut: str = "", niveau: str = "", profil: str = "",
                         metier: str = "", skip: int = 0, limit: int = 100):
    query: dict = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"entreprise": rx}, {"ville": rx}, {"telephone": rx}, {"email": rx}]
    if statut:
        query["statut"] = statut
    if niveau:
        query["niveau_conversion"] = niveau
    if profil:
        query["profil"] = profil
    if metier:
        query["metier"] = {"$regex": re.escape(metier), "$options": "i"}
    total = await db.prospects.count_documents(query)
    items = await db.prospects.find(query, {"_id": 0}).sort(
        [("score_conversion", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total}


@api_router.get("/prospects/{prospect_id}")
async def get_prospect(prospect_id: str):
    p = await db.prospects.find_one({"id": prospect_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Prospect introuvable")
    settings = await get_settings()
    item = await build_queue_item(p, settings)
    scenario = await get_scenario(p.get("profil", "site_moyen"))
    etapes = scenario.get("etapes", [])
    plan = p.get("plan_canaux") or canal_plan(p, len(etapes) or 4)
    apercu = []
    for i, e in enumerate(etapes):
        canal_step = plan[i] if i < len(plan) else item["canal"]
        entry = {"etape": e["etape"], "canal": canal_step, "delai_jours": e["delai_jours"],
                 "message": render_message(step_template(e, canal_step), p, settings)}
        if canal_step == "email":
            entry["objet"] = render_message(pick_objet(e, p.get("variante_ab", "A")), p, settings)
        apercu.append(entry)
    item["sequence"] = apercu
    return item


@api_router.patch("/prospects/{prospect_id}")
async def update_prospect(prospect_id: str, body: ProspectUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Aucune modification")
    if "telephone" in updates:
        updates["telephone"] = normalize_french_phone(updates["telephone"])
        updates["tel_digits"] = phone_digits(updates["telephone"])
    if "statut" in updates and updates["statut"] == "a_contacter":
        updates["date_prochaine_action"] = now_iso()
    if {"telephone", "email", "linkedin_url"} & set(updates):
        p = await db.prospects.find_one({"id": prospect_id}, {"_id": 0})
        if not p:
            raise HTTPException(404, "Prospect introuvable")
        deja_contacte = any(h.get("type") in ("envoye", "email_envoye")
                            for h in p.get("historique", []))
        if not deja_contacte:  # le plan multi-canal est figé dès le premier envoi
            merged = {**p, **updates}
            scenario = await get_scenario(merged.get("profil", "site_moyen"))
            plan = canal_plan(merged, len(scenario.get("etapes", [])) or 4)
            updates["plan_canaux"] = plan
            updates["canal_contact"] = plan[0] if plan else ""
    res = await db.prospects.update_one({"id": prospect_id}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(404, "Prospect introuvable")
    return await db.prospects.find_one({"id": prospect_id}, {"_id": 0})


@api_router.delete("/prospects/{prospect_id}")
async def delete_prospect(prospect_id: str):
    res = await db.prospects.delete_one({"id": prospect_id})
    if not res.deleted_count:
        raise HTTPException(404, "Prospect introuvable")
    return {"ok": True}


@api_router.post("/prospects/{prospect_id}/action")
async def prospect_action(prospect_id: str, body: ActionRequest):
    p = await db.prospects.find_one({"id": prospect_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Prospect introuvable")

    action = body.type
    event = {"type": action, "date": now_iso(), "etape": p.get("etape_relance", 1)}
    updates: dict = {}

    if action == "envoye":
        scenario = await get_scenario(p.get("profil", "site_moyen"))
        etapes = scenario.get("etapes", [])
        if etapes:  # conserve le message réellement envoyé dans l'historique
            settings = await get_settings()
            idx = min(max(int(p.get("etape_relance", 1)) - 1, 0), len(etapes) - 1)
            event["canal"] = p.get("canal_contact", "")
            event["message"] = as_str(p.get("message_personnalise")) or render_message(
                step_template(etapes[idx], event["canal"]), p, settings)
            if event["canal"] == "email":
                event["variante"] = p.get("variante_ab", "A")
                event["objet_template"] = pick_objet(etapes[idx], p.get("variante_ab", "A"))
        updates.update(advance_updates(p, etapes))
    elif action == "skip":
        updates["date_prochaine_action"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif action == "rappel":
        jours = max(1, min(int(body.rappel_dans_jours or 7), 90))
        rappel_date = (datetime.now(timezone.utc) + timedelta(days=jours)).isoformat()
        updates["date_prochaine_action"] = rappel_date
        updates["date_rappel"] = rappel_date
        event["jours"] = jours
    elif action in ("repondu", "rdv"):
        updates["statut"] = action
    elif action in ("perdu", "opt_out"):
        updates["statut"] = action
        if body.raison_refus:
            updates["raison_refus"] = body.raison_refus
            event["raison_refus"] = body.raison_refus
    elif action == "gagne":
        updates["statut"] = action
        if body.ca_contrat is not None:
            updates["ca_contrat"] = body.ca_contrat
            event["ca_contrat"] = body.ca_contrat
    elif action == "reactiver":
        updates["statut"] = "a_contacter"
        updates["etape_relance"] = 1
        updates["date_prochaine_action"] = now_iso()
        updates["date_rappel"] = None
    else:
        raise HTTPException(400, f"Action inconnue : {action}")

    await db.prospects.update_one(
        {"id": prospect_id}, {"$set": updates, "$push": {"historique": event}})
    return await db.prospects.find_one({"id": prospect_id}, {"_id": 0})


# ============================================================ Import CSV / Excel

def _norm_col(col: str) -> str:
    c = unicodedata.normalize("NFKD", str(col))
    c = "".join(ch for ch in c if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()


COL_MAP = [
    (("entreprise", "nom entreprise", "nom complet", "societe", "raison sociale", "nom"), "entreprise"),
    (("metier", "secteur", "activite"), "metier"),
    (("ville", "commune"), "ville"),
    (("code postal", "cp"), "code_postal"),
    (("adresse",), "adresse"),
    (("siren", "siret"), "siren"),
    (("telephone", "tel", "phone", "portable", "mobile"), "telephone"),
    (("email", "mail", "courriel"), "email"),
    (("site web", "site", "site url", "website", "url"), "site_web"),
    (("linkedin url", "linkedin"), "linkedin_url"),
    (("note site", "note"), "note_site"),
    (("qualite site", "qualite"), "qualite_site"),
    (("score conversion", "score"), "score_conversion"),
    (("niveau conversion", "niveau"), "niveau_conversion"),
    (("signal principal", "signal"), "signal_principal"),
    (("signaux conversion", "signaux"), "signaux_conversion"),
    (("pistes amelioration", "opportunites", "pistes"), "opportunites"),
    (("message whatsapp", "whatsapp"), "message_whatsapp"),
    (("message linkedin",), "message_linkedin"),
    (("source",), "source"),
]


def map_columns(columns: list[str]) -> dict[str, str]:
    mapping = {}
    used = set()
    for col in columns:
        norm = _norm_col(col)
        for aliases, target in COL_MAP:
            if target in used:
                continue
            if norm in aliases or any(norm.startswith(a) for a in aliases):
                mapping[col] = target
                used.add(target)
                break
    return mapping


@api_router.post("/import")
async def import_file(file: UploadFile = File(...)):
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            try:
                df = pd.read_csv(io.BytesIO(content), sep=None, engine="python")
            except Exception:
                df = pd.read_csv(io.BytesIO(content), sep=";", encoding="latin-1")
    except Exception as e:
        raise HTTPException(400, f"Fichier illisible : {e}")

    mapping = map_columns(list(df.columns))
    if "entreprise" not in mapping.values():
        raise HTTPException(400, "Colonne 'entreprise' (ou 'nom') introuvable dans le fichier.")

    importes, doublons, erreurs, sans_contact = 0, 0, 0, 0
    for _, row in df.iterrows():
        data = {}
        for col, target in mapping.items():
            val = row[col]
            data[target] = "" if pd.isna(val) else val
        if not as_str(data.get("entreprise")):
            erreurs += 1
            continue
        data["site_web"] = resolve_site_web(data.get("site_web", "")) if as_str(data.get("site_web")) else ""
        p = prepare_new_prospect(data)
        if not p["canal_contact"]:
            sans_contact += 1
            continue
        if await find_duplicate(p):
            doublons += 1
            continue
        await db.prospects.insert_one(p)
        importes += 1

    return {"importes": importes, "doublons": doublons, "erreurs": erreurs,
            "sans_contact": sans_contact, "colonnes_reconnues": list(mapping.values())}


# ============================================================ Scraper (jobs en arrière-plan)

@api_router.get("/metiers")
async def get_metiers():
    return {"metiers": METIERS}


async def _job_log(job_id: str, message: str, **updates):
    upd = {"$push": {"logs": f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}"}}
    if updates:
        upd["$set"] = updates
    await db.jobs.update_one({"id": job_id}, upd)


async def run_scrape_job(job_id: str, params: ScrapeRequest):
    try:
        settings = await get_settings()
        serper_key = as_str(settings.get("serper_api_key"))
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as http:
            combos = [(m, v) for m in params.metiers for v in params.villes]
            items: list[dict] = []
            for n, (metier, ville) in enumerate(combos, 1):
                await _job_log(job_id,
                               f"Découverte via {params.source} ({n}/{len(combos)}) : {metier} à {ville}…",
                               statut="decouverte", progress=min(2 + int(n / len(combos) * 13), 15))
                try:
                    if params.source == "osm":
                        found = await discover_osm(http, metier, ville, limite=params.limite)
                    else:
                        found = await discover_gouv(http, metier, ville, params.departement, params.limite)
                except Exception as e:
                    await _job_log(job_id, f"⚠️ {metier} à {ville} : {e}")
                    found = []
                items.extend(found)
            await _job_log(job_id, f"{len(items)} entreprises découvertes", total=len(items), progress=15)

            if not items:
                await _job_log(job_id, "Aucun résultat — élargir la recherche ?", statut="termine", progress=100)
                return

            sem = asyncio.Semaphore(4)
            ajoutes, doublons, sans_contact = 0, 0, 0
            traites = 0
            lock = asyncio.Lock()

            async def process(item: dict):
                nonlocal ajoutes, doublons, sans_contact, traites
                async with sem:
                    try:
                        if serper_key and not has_real_website(item.get("site_web", "")):
                            item["site_web"] = await serper_find_site(
                                http, serper_key, item["entreprise"], item.get("ville", ""), item.get("metier", ""))
                        # Enrichissement contact toujours actif (le canal en dépend)
                        if has_real_website(item.get("site_web", "")) and not item.get("telephone"):
                            item["telephone"] = await enrich_phone(http, item["site_web"])
                        if has_real_website(item.get("site_web", "")) and not as_str(item.get("email")):
                            item["email"] = await enrich_email(http, item["site_web"])
                        if params.auditer:
                            audit = await audit_site(http, item.get("site_web", ""),
                                                     item.get("telephone", ""), item.get("metier", ""))
                            item.update(audit)
                        p = prepare_new_prospect(item)
                        async with lock:
                            if not p["canal_contact"]:
                                sans_contact += 1  # ni email, ni téléphone, ni LinkedIn → ignoré
                            elif await find_duplicate(p):
                                doublons += 1
                            else:
                                await db.prospects.insert_one(p)
                                ajoutes += 1
                    except Exception as e:
                        logger.warning(f"Erreur prospect {item.get('entreprise')}: {e}")
                    finally:
                        traites += 1
                        pct = 15 + int(traites / len(items) * 80)
                        await db.jobs.update_one({"id": job_id}, {"$set": {
                            "progress": pct, "traites": traites, "ajoutes": ajoutes,
                            "doublons": doublons, "sans_contact": sans_contact}})

            await _job_log(job_id, "Enrichissement + audit des sites…", statut="audit")
            await asyncio.gather(*[process(i) for i in items])
            await _job_log(job_id,
                           f"Terminé : {ajoutes} prospects ajoutés, {doublons} doublons ignorés, "
                           f"{sans_contact} sans aucun contact (email/tél/LinkedIn) écartés.",
                           statut="termine", progress=100, ajoutes=ajoutes,
                           doublons=doublons, sans_contact=sans_contact)
    except Exception as e:
        logger.exception("Job scraping en erreur")
        await _job_log(job_id, f"Erreur : {e}", statut="erreur")


async def run_enrich_emails_job(job_id: str):
    """Backfill : cherche l'email sur le site des prospects qui n'en ont pas."""
    try:
        vide = {"$not": {"$regex": r"\S"}}
        prospects = await db.prospects.find(
            {"email": vide, "site_web": {"$regex": "^http"}}, {"_id": 0}).to_list(2000)
        total = len(prospects)
        await _job_log(job_id, f"Recherche d'emails sur {total} sites…", statut="en_cours", total=total)
        trouves, traites = 0, 0
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(6)

        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as http:
            async def process(p: dict):
                nonlocal trouves, traites
                email = ""
                async with sem:
                    try:
                        email = await enrich_email(http, p["site_web"])
                    except Exception:
                        pass
                async with lock:
                    traites += 1
                    if email:
                        trouves += 1
                        updates = {"email": email}
                        deja_contacte = any(h.get("type") in ("envoye", "email_envoye")
                                            for h in p.get("historique", []))
                        if not deja_contacte:  # canal figé dès le premier envoi
                            updates["canal_contact"] = "email"
                        await db.prospects.update_one({"id": p["id"]}, {"$set": updates})
                    await db.jobs.update_one({"id": job_id}, {"$set": {
                        "progress": int(traites / max(total, 1) * 100),
                        "traites": traites, "trouves": trouves}})

            await asyncio.gather(*[process(p) for p in prospects])
        await _job_log(job_id, f"Terminé : {trouves} emails trouvés sur {total} sites visités.",
                       statut="termine", progress=100)
    except Exception as e:
        logger.exception("Job enrichissement emails en erreur")
        await _job_log(job_id, f"Erreur : {e}", statut="erreur")


@api_router.post("/prospects/enrich-emails")
async def start_enrich_emails():
    job = {"id": str(uuid.uuid4()), "type": "enrich_emails", "statut": "demarre",
           "progress": 0, "total": 0, "traites": 0, "trouves": 0,
           "logs": [], "created_at": now_iso()}
    await db.jobs.insert_one({**job})
    asyncio.create_task(run_enrich_emails_job(job["id"]))
    return {k: v for k, v in job.items() if k != "_id"}



@api_router.post("/scrape")
async def start_scrape(params: ScrapeRequest):
    job = {"id": str(uuid.uuid4()), "params": params.model_dump(), "statut": "demarre",
           "progress": 0, "total": 0, "traites": 0, "ajoutes": 0, "doublons": 0,
           "sans_contact": 0, "logs": [], "created_at": now_iso()}
    await db.jobs.insert_one({**job})
    asyncio.create_task(run_scrape_job(job["id"], params))
    return {k: v for k, v in job.items() if k != "_id"}


@api_router.get("/scrape/jobs")
async def list_jobs():
    jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"jobs": jobs}


@api_router.get("/scrape/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job introuvable")
    return job


# ============================================================ Scénarios & Templates

@api_router.get("/scenarios")
async def list_scenarios():
    out = []
    for profil in PROFILS:
        out.append(await get_scenario(profil))
    return {"scenarios": out}


@api_router.put("/scenarios/{profil}")
async def update_scenario(profil: str, body: ScenarioUpdate):
    if profil not in PROFILS:
        raise HTTPException(404, "Profil inconnu")
    base = DEFAULT_SCENARIOS[profil]
    doc = {"profil": profil, "label": base["label"], "description": base["description"],
           "version": base.get("version", 1), "etapes": [e.model_dump() for e in body.etapes]}
    await db.scenarios.update_one({"profil": profil}, {"$set": doc}, upsert=True)
    return doc


# ============================================================ IA — amélioration de message

@api_router.post("/ai/improve")
async def ai_improve(body: AIImproveRequest):
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

    contexte = ""
    if body.prospect_id:
        p = await db.prospects.find_one({"id": body.prospect_id}, {"_id": 0})
        if p:
            contexte = (f"Prospect : {p.get('entreprise')} ({p.get('metier')}, {p.get('ville')}). "
                        f"Site : {p.get('site_web') or 'aucun'} (note {p.get('note_site')}/100). "
                        f"Signal d'achat : {p.get('signal_principal') or 'aucun'}. "
                        f"Pistes : {p.get('opportunites', '')[:300]}")

    limite = 380 if body.canal == "whatsapp" else 290
    system = (
        "Tu es un expert en prospection B2B française auprès d'artisans (plombiers, électriciens…). "
        "Tu améliores des messages de premier contact ou de relance envoyés via WhatsApp ou LinkedIn. "
        "Règles : français naturel et direct, vouvoiement, ton humain et léger (pas commercial agressif), "
        f"maximum {limite} caractères, pas de formules creuses, garde les liens et noms propres intacts, "
        "termine par une question simple qui appelle une réponse. Réponds UNIQUEMENT avec le message amélioré, rien d'autre."
    )
    prompt = f"{contexte}\n\nCanal : {body.canal}\n"
    if body.instruction:
        prompt += f"Consigne : {body.instruction}\n"
    prompt += f"\nMessage à améliorer :\n{body.message}"

    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"improve-{uuid.uuid4()}",
        system_message=system,
    ).with_model("openai", os.environ.get("AI_MODEL", "gpt-5"))

    full = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                full += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.exception("Erreur IA")
        raise HTTPException(502, f"Erreur génération IA : {e}")

    return {"message": full.strip().strip('"')}


@api_router.post("/ai/mini-audit")
async def ai_mini_audit(body: MiniAuditRequest):
    """Génère un mini-audit conversion-friendly (sans note, sans jargon) prêt à envoyer."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

    p = await db.prospects.find_one({"id": body.prospect_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Prospect introuvable")
    settings = await get_settings()
    prenom = as_str(settings.get("prenom_expediteur")) or "Simon"
    lien_rdv = as_str(settings.get("lien_rdv"))

    has_site = has_real_website(p.get("site_web", ""))
    system = (
        f"Tu écris des mini-audits de présence en ligne pour des artisans français, envoyés via WhatsApp par {prenom}, spécialiste web. "
        "INTERDICTIONS ABSOLUES : aucun jargon technique (jamais de SEO, HTTPS, SSL, meta, responsive, balise, viewport, CMS, référencement naturel…), "
        "aucune note ni score, aucun pourcentage, pas plus de 3 constats. "
        "Traduis tout en bénéfices ou risques CONCRETS pour l'artisan : être trouvé (ou pas) quand un client cherche sur Google, "
        "recevoir des appels facilement depuis un téléphone, permettre une demande de devis en 30 secondes, rassurer avec photos de chantiers et avis clients. "
        "Ton chaleureux, direct, vouvoiement, comme un message WhatsApp humain. "
        "Format : 1 phrase d'intro personnalisée (ce que j'ai regardé), puis 2-3 constats courts commençant par ✅ (point fort) ou ⚠️ (manque à gagner), "
        f"puis 1 phrase de conclusion avec proposition d'un échange rapide{' incluant ce lien : ' + lien_rdv if lien_rdv else ''}. "
        "Maximum 750 caractères. Réponds UNIQUEMENT avec le message, rien d'autre."
    )
    prompt = (
        f"Entreprise : {p.get('entreprise')} — {p.get('metier')} à {p.get('ville')}.\n"
        f"Site web : {p.get('site_web') if has_site else 'AUCUN site trouvé'}.\n"
        f"Constats techniques bruts (à traduire en langage client, sans jargon) : {p.get('opportunites', 'aucun')[:500]}\n"
        f"Signal principal : {p.get('signal_principal') or 'aucun'}.\n"
        f"Téléphone trouvé : {'oui' if p.get('telephone') else 'non'}.\n\n"
        "Écris le mini-audit."
    )

    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"mini-audit-{uuid.uuid4()}",
        system_message=system,
    ).with_model("openai", os.environ.get("AI_MODEL", "gpt-5"))

    full = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                full += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.exception("Erreur mini-audit IA")
        raise HTTPException(502, f"Erreur génération IA : {e}")

    audit = full.strip().strip('"')
    await db.prospects.update_one({"id": body.prospect_id}, {"$set": {"mini_audit": audit}})
    return {"mini_audit": audit, "wa_link": build_wa_link(p.get("telephone", ""), audit)}


@api_router.get("/dashboard/scenario-stats")
async def scenario_stats():
    """Stats de réponse par scénario/profil."""
    out = []
    for profil in PROFILS:
        total = await db.prospects.count_documents({"profil": profil})
        contactes = await db.prospects.count_documents({"profil": profil, "historique.type": "envoye"})
        repondus = await db.prospects.count_documents(
            {"profil": profil, "statut": {"$in": ["repondu", "rdv", "gagne"]}})
        rdv = await db.prospects.count_documents({"profil": profil, "statut": {"$in": ["rdv", "gagne"]}})
        out.append({"profil": profil, "label": PROFIL_LABELS[profil], "total": total,
                    "contactes": contactes, "repondus": repondus, "rdv": rdv,
                    "taux_reponse": round(repondus / contactes * 100, 1) if contactes else 0.0})
    return {"stats": out}


EXPORT_COLS = [
    ("entreprise", "Entreprise"), ("metier", "Métier"), ("ville", "Ville"),
    ("code_postal", "Code postal"), ("adresse", "Adresse"), ("siren", "SIREN"),
    ("telephone", "Téléphone"), ("email", "Email"), ("site_web", "Site web"),
    ("linkedin_url", "LinkedIn"), ("canal_contact", "Canal"), ("note_site", "Note site (/100)"),
    ("qualite_site", "Qualité site"), ("score_conversion", "Score conversion (/100)"),
    ("niveau_conversion", "Niveau"), ("profil", "Profil"), ("statut", "Statut"),
    ("etape_relance", "Étape relance"), ("signal_principal", "Signal principal"),
    ("opportunites", "Pistes d'amélioration"), ("mini_audit", "Mini-audit"),
    ("notes", "Notes"), ("source", "Source"), ("created_at", "Ajouté le"),
]


@api_router.get("/export/prospects")
async def export_prospects(q: str = "", statut: str = "", niveau: str = "", profil: str = ""):
    query: dict = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"entreprise": rx}, {"ville": rx}, {"telephone": rx}, {"email": rx}]
    if statut:
        query["statut"] = statut
    if niveau:
        query["niveau_conversion"] = niveau
    if profil:
        query["profil"] = profil
    items = await db.prospects.find(query, {"_id": 0}).sort("score_conversion", -1).to_list(5000)
    rows = [{label: p.get(key, "") for key, label in EXPORT_COLS} for p in items]
    df = pd.DataFrame(rows, columns=[label for _, label in EXPORT_COLS])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prospects")
    buf.seek(0)
    fname = f"prospects_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ============================================================ Email (SendGrid)

@api_router.post("/email/send")
async def email_send(body: EmailSendRequest):
    settings = await get_settings()
    key = as_str(settings.get("sendgrid_api_key"))
    sender = as_str(settings.get("email_expediteur"))
    if not key or not sender:
        raise HTTPException(400, "SENDGRID_NON_CONFIGURE")
    p = await db.prospects.find_one({"id": body.prospect_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Prospect introuvable")
    to = as_str(p.get("email"))
    if not to:
        raise HTTPException(400, "Pas d'adresse email pour ce prospect")
    try:
        status = await asyncio.to_thread(
            send_email_sync, key, sender, as_str(settings.get("prenom_expediteur")),
            to, body.subject, body.message, as_str(settings.get("email_reponse")))
    except Exception as e:
        raise HTTPException(502, f"Erreur SendGrid : {e}")
    if status not in (200, 201, 202):
        raise HTTPException(502, f"SendGrid a répondu {status}")
    await db.email_log.insert_one({
        "id": str(uuid.uuid4()), "prospect_id": body.prospect_id,
        "entreprise": as_str(p.get("entreprise")), "destinataire": to,
        "objet": body.subject, "etape": p.get("etape_relance", 1),
        "message": body.message, "auto": False, "statut": "envoye", "date": now_iso()})
    await db.prospects.update_one(
        {"id": body.prospect_id},
        {"$push": {"historique": {"type": "email_envoye", "canal": "email", "date": now_iso(),
                                  "etape": p.get("etape_relance", 1),
                                  "objet": body.subject, "message": body.message}}})
    return {"ok": True, "to": to}


# ============================================================ Pilote automatique

@api_router.get("/autopilot/status")
async def autopilot_status():
    settings = await get_settings()
    actif = bool(settings.get("autopilot_actif"))
    configure = bool(as_str(settings.get("sendgrid_api_key")) and as_str(settings.get("email_expediteur")))
    quota = int(settings.get("autopilot_quota_jour", 50) or 50)
    deja = await count_sent_today(db)
    candidats = await eligible_prospects(db)
    fenetre_ok, raison_fenetre = in_window(settings)
    raison_pause = ""
    if not actif:
        raison_pause = "Pilote automatique désactivé"
    elif not configure:
        raison_pause = "SendGrid non configuré (clé ou email expéditeur manquant)"
    elif deja >= quota:
        raison_pause = f"Quota journalier atteint ({deja}/{quota})"
    elif not fenetre_ok:
        raison_pause = raison_fenetre
    return {"actif": actif, "configure": configure,
            "envoyes_aujourdhui": deja, "quota": quota,
            "en_attente": len(candidats), "fenetre_ok": fenetre_ok,
            "raison_pause": raison_pause}


@api_router.post("/autopilot/run")
async def autopilot_run():
    """Déclenchement manuel d'un passage (ignore l'interrupteur et la plage horaire)."""
    return await run_tick(db, force=True)


@api_router.get("/autopilot/log")
async def autopilot_log(limit: int = 50):
    items = await db.email_log.find({}, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    return {"items": items}


# ============================================================ Paramètres

@api_router.get("/settings")
async def read_settings():
    s = await get_settings()
    return {"prenom_expediteur": s.get("prenom_expediteur", ""),
            "lien_rdv": s.get("lien_rdv", ""),
            "offre": s.get("offre", ""),
            "serper_api_key": s.get("serper_api_key", ""),
            "sendgrid_api_key": s.get("sendgrid_api_key", ""),
            "email_expediteur": s.get("email_expediteur", ""),
            "email_reponse": s.get("email_reponse", ""),
            "webhook_token": s.get("webhook_token", ""),
            "autopilot_actif": bool(s.get("autopilot_actif", False)),
            "autopilot_quota_jour": int(s.get("autopilot_quota_jour", 50) or 50),
            "autopilot_heure_debut": int(s.get("autopilot_heure_debut", 9) or 0),
            "autopilot_heure_fin": int(s.get("autopilot_heure_fin", 18) or 24),
            "autopilot_jours_ouvres": bool(s.get("autopilot_jours_ouvres", True)),
            "imap_host": s.get("imap_host", ""),
            "imap_port": int(s.get("imap_port", 993) or 993),
            "imap_user": s.get("imap_user", ""),
            # On renvoie un placeholder pour ne pas exposer le mot de passe
            "imap_password_set": bool(s.get("imap_password")),
            "imap_folder": s.get("imap_folder", "INBOX")}


@api_router.put("/settings")
async def write_settings(body: SettingsUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.settings.update_one({"_id": "global"}, {"$set": updates}, upsert=True)
    return await read_settings()


# ============================================================ Import depuis SendGrid

class SendgridImportRequest(BaseModel):
    since_days: int = 30
    dry_run: bool = False
    mark_step1_sent: bool = True  # marquer l'étape 1 comme déjà envoyée → autopilot programmera l'étape 2


@api_router.post("/import/sendgrid")
async def import_from_sendgrid(body: SendgridImportRequest):
    """Réimporte les prospects depuis l'historique d'envoi SendGrid.

    Lit la clé API et l'email expéditeur depuis les settings. Récupère tous les
    envois récents via /v3/messages, dédoublonne par destinataire, crée les
    prospects manquants avec canal=email et marque l'étape 1 comme envoyée
    (autopilot prendra le relais pour l'étape 2).
    """
    s = await get_settings()
    api_key = s.get("sendgrid_api_key", "")
    from_email = s.get("email_expediteur", "")
    if not api_key or not from_email:
        raise HTTPException(
            status_code=400,
            detail="Clé SendGrid et email expéditeur requis dans Paramètres.",
        )

    messages = await fetch_sent_messages(api_key, from_email, since_days=body.since_days)
    by_recipient = aggregate_by_recipient(messages, self_email=from_email)

    summary = {
        "messages_fetched": len(messages),
        "unique_recipients": len(by_recipient),
        "created": 0,
        "skipped_existing": 0,
        "errors": 0,
        "preview": [],  # 10 premiers prospects à créer (pour dry-run)
    }

    if body.dry_run:
        preview = []
        for to_email, m in list(by_recipient.items())[:10]:
            preview.append({
                "email": to_email,
                "entreprise": _entreprise_from_email_or_subject(to_email, m.get("subject", "")),
                "site_web": _extract_site_from_subject(m.get("subject", "")),
                "last_event": m.get("last_event_time"),
                "subject": m.get("subject"),
                "opens": m.get("opens_count", 0),
                "clicks": m.get("clicks_count", 0),
                "status": m.get("status"),
            })
        summary["preview"] = preview
        return summary

    scenario = await get_scenario("site_moyen")  # par défaut, ajusté ensuite si audit
    etapes_default = scenario.get("etapes", [])

    for to_email, m in by_recipient.items():
        try:
            # Skip si email déjà en base
            existing = await db.prospects.find_one({"email": to_email}, {"_id": 0, "id": 1})
            if existing:
                summary["skipped_existing"] += 1
                continue

            subject = m.get("subject", "")
            site = _extract_site_from_subject(subject)
            entreprise = _entreprise_from_email_or_subject(to_email, subject)
            last_event = m.get("last_event_time", "")  # ex "2026-06-11T21:56:11Z"

            raw = {
                "entreprise": entreprise,
                "email": to_email,
                "site_web": site,
                "source": "sendgrid_reimport",
            }
            p = prepare_new_prospect(raw)
            p["canal_contact"] = "email"

            # Construire l'historique : étape 1 envoyée à `last_event`
            historique_entry = {
                "type": "envoye",
                "date": last_event,
                "etape": 1,
                "canal": "email",
                "objet": subject,
                "message": "",
                "source": "sendgrid_reimport",
                "opens": int(m.get("opens_count", 0) or 0),
                "clicks": int(m.get("clicks_count", 0) or 0),
                "sendgrid_msg_id": m.get("msg_id"),
                "sendgrid_status": m.get("status"),
            }
            p["historique"] = [historique_entry]

            if body.mark_step1_sent and etapes_default:
                # Programmer l'étape 2 à last_event + delai_jours[1]
                step2 = etapes_default[1] if len(etapes_default) > 1 else None
                if step2:
                    delai = int(step2.get("delai_jours", 3))
                    base_dt = datetime.fromisoformat(last_event.replace("Z", "+00:00"))
                    p["etape_relance"] = 2
                    p["date_prochaine_action"] = (base_dt + timedelta(days=delai)).isoformat()
                else:
                    p["statut"] = "epuise"
                p["derniere_action"] = "envoye_etape_1"

            await db.prospects.insert_one(p)
            summary["created"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Import SendGrid : erreur sur %s (%s)", to_email, exc)
            summary["errors"] += 1

    # Dump immédiat pour sécuriser la réimportation
    try:
        await dump_db(db)
    except Exception:  # noqa: BLE001
        pass

    return summary


# ============================================================ Récupération des réponses

class RepliesImportRequest(BaseModel):
    since_days: int = 30
    dry_run: bool = False


@api_router.post("/import/replies")
async def import_replies_from_sendgrid(body: RepliesImportRequest):
    """Récupère les réponses prospects depuis l'historique SendGrid.

    Méthode : le webhook /sendgrid/inbound re-envoie chaque réponse à l'utilisateur
    sous la forme "[Réponse prospect] Re: <subject>". On lit ces notifications
    via /v3/messages, on les croise avec les envois sortants pour identifier
    quel prospect a répondu, puis on marque les prospects.
    """
    s = await get_settings()
    api_key = s.get("sendgrid_api_key", "")
    self_email = s.get("email_expediteur", "")
    if not api_key or not self_email:
        raise HTTPException(400, "Clé SendGrid et email expéditeur requis dans Paramètres.")

    notifications = await fetch_notifications(api_key, self_email, since_days=body.since_days)
    outgoing = await fetch_outgoing(api_key, self_email, since_days=body.since_days)
    matches = match_notifications_to_outgoing(notifications, outgoing)

    summary = {
        "notifications_found": len(notifications),
        "outgoing_indexed": len(outgoing),
        "matched": sum(1 for x in matches if x["matched"]),
        "unmatched": sum(1 for x in matches if not x["matched"]),
        "prospects_updated": 0,
        "orphans_saved": 0,
        "details": [],
    }

    if body.dry_run:
        summary["details"] = matches[:20]
        return summary

    for entry in matches:
        try:
            reply_at = entry["reply_at"]
            prospect_email = entry["prospect_email"]
            orig_subject = entry["original_subject"]

            if prospect_email:
                p = await db.prospects.find_one(
                    {"email": {"$regex": f"^{re.escape(prospect_email)}$", "$options": "i"}},
                    {"_id": 0, "id": 1, "entreprise": 1, "statut": 1},
                )
            else:
                p = None

            history_entry = {
                "type": "reponse_email",
                "action": "repondu",
                "date": reply_at,
                "objet": orig_subject,
                "source": "sendgrid_recovery",
                "sendgrid_msg_id": entry["notif_msg_id"],
            }
            reponse_doc = {
                "id": str(uuid.uuid4()),
                "de": prospect_email or "",
                "objet": orig_subject,
                "texte": "(contenu non disponible — récupéré via SendGrid Activity, voir boîte email)",
                "action": "repondu",
                "prospect_id": p["id"] if p else None,
                "entreprise": (p.get("entreprise") if p else "") or "",
                "date": reply_at,
                "source": "sendgrid_recovery",
            }

            # Insertion en upsert sur le msg_id pour idempotence
            existing_reply = await db.reponses.find_one(
                {"sendgrid_msg_id": entry["notif_msg_id"]}
            )
            if existing_reply:
                continue  # déjà importé
            reponse_doc["sendgrid_msg_id"] = entry["notif_msg_id"]
            await db.reponses.insert_one(reponse_doc)

            if p:
                # Met à jour le prospect (sans écraser opt_out si déjà désabonné)
                current_statut = p.get("statut")
                new_statut = "repondu" if current_statut not in ("opt_out", "rdv_pris") else current_statut
                await db.prospects.update_one(
                    {"id": p["id"]},
                    {"$set": {"statut": new_statut, "reply_action": "repondu"},
                     "$push": {"historique": history_entry}},
                )
                summary["prospects_updated"] += 1
            else:
                summary["orphans_saved"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Import réponses : erreur (%s)", exc)

    try:
        await dump_db(db)
    except Exception:
        pass

    return summary


@api_router.get("/replies")
async def list_replies(limit: int = 200, only_linked: bool = True):
    """Liste les réponses, les plus récentes en premier.

    only_linked=True (par défaut) : ne renvoie que les réponses liées à un prospect.
    """
    query = {"prospect_id": {"$ne": None}} if only_linked else {}
    items = await db.reponses.find(query, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    total_all = await db.reponses.count_documents({})
    total_linked = await db.reponses.count_documents({"prospect_id": {"$ne": None}})
    return {
        "items": items,
        "count": len(items),
        "total_all": total_all,
        "total_linked": total_linked,
        "total_orphans": total_all - total_linked,
    }


# ============================================================ Boîte mail IMAP

class InboxSyncRequest(BaseModel):
    since_days: int = 30
    dry_run: bool = False
    prospects_only: bool = True  # n'enregistre que les réponses liées à un prospect


@api_router.post("/inbox/test")
async def inbox_test():
    """Teste la connexion IMAP avec les paramètres en base."""
    s = await get_settings()
    host = s.get("imap_host", "")
    user = s.get("imap_user", "") or s.get("email_expediteur", "")
    password = s.get("imap_password", "")
    port = int(s.get("imap_port", 993) or 993)
    if not host or not user or not password:
        raise HTTPException(400, "Host, utilisateur et mot de passe IMAP requis.")
    return await test_imap_connection(host, port, user, password)


@api_router.post("/inbox/sync")
async def inbox_sync(body: InboxSyncRequest):
    """Lit la boîte mail IMAP, identifie les réponses prospects, met à jour la base."""
    s = await get_settings()
    host = s.get("imap_host", "")
    user = s.get("imap_user", "") or s.get("email_expediteur", "")
    password = s.get("imap_password", "")
    port = int(s.get("imap_port", 993) or 993)
    folder = s.get("imap_folder", "INBOX") or "INBOX"
    self_email = s.get("email_expediteur", "") or user
    if not host or not user or not password:
        raise HTTPException(400, "Configurez d'abord les paramètres IMAP.")

    try:
        messages = await fetch_recent_messages(
            host=host, port=port, user=user, password=password,
            since_days=body.since_days, folder=folder, self_email=self_email,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"IMAP : {type(exc).__name__} : {exc}") from exc

    summary = {
        "messages_read": len(messages),
        "linked": 0,           # réponses liées à un prospect
        "orphans": 0,          # réponses sans prospect correspondant (non enregistrées si prospects_only=True)
        "ignored_non_prospect": 0,  # nb de mails non-prospects ignorés
        "already_imported": 0,
        "prospects_updated": 0,
        "details": [],
    }

    if body.dry_run:
        # Pour le dry-run, on annote chaque mail avec si oui ou non c'est un prospect
        details = []
        for m in messages[:50]:
            p = await db.prospects.find_one(
                {"email": {"$regex": f"^{re.escape(m['from_email'])}$", "$options": "i"}},
                {"_id": 0, "id": 1, "entreprise": 1},
            ) if m['from_email'] else None
            details.append({
                "from_email": m["from_email"],
                "from_name": m["from_name"],
                "subject": m["subject"],
                "date": m["date"],
                "excerpt": m["body_excerpt"],
                "is_prospect": bool(p),
                "entreprise": p.get("entreprise") if p else "",
            })
        summary["details"] = details
        summary["would_link"] = sum(1 for d in details if d["is_prospect"])
        summary["would_ignore"] = sum(1 for d in details if not d["is_prospect"])
        return summary

    for m in messages:
        try:
            from_email = m["from_email"]
            if not from_email:
                continue
            message_id = m.get("message_id") or ""
            # Idempotence : skip si déjà importé (par Message-ID)
            if message_id:
                existing = await db.reponses.find_one({"imap_message_id": message_id})
                if existing:
                    summary["already_imported"] += 1
                    continue

            p = await db.prospects.find_one(
                {"email": {"$regex": f"^{re.escape(from_email)}$", "$options": "i"}},
                {"_id": 0, "id": 1, "entreprise": 1, "statut": 1},
            )

            # Si on filtre, ignorer les non-prospects (les newsletters, factures, perso, etc.)
            if body.prospects_only and not p:
                summary["ignored_non_prospect"] += 1
                continue

            action = classify(m["body"], m["subject"])
            now = datetime.now(timezone.utc).isoformat()
            reponse_doc = {
                "id": str(uuid.uuid4()),
                "de": from_email,
                "de_complet": m["from_name"] or from_email,
                "objet": m["subject"][:300],
                "texte": m["body"][:4000],
                "extrait": m["body_excerpt"],
                "action": action,
                "prospect_id": p["id"] if p else None,
                "entreprise": (p.get("entreprise") if p else "") or "",
                "date": m["date"] or now,
                "source": "imap",
                "imap_message_id": message_id,
                "imap_uid": m["uid"],
            }
            await db.reponses.insert_one(reponse_doc)

            if p:
                current_statut = p.get("statut")
                if action == "desabonne":
                    new_statut = "opt_out"
                elif action == "interesse":
                    new_statut = "interesse" if current_statut not in ("opt_out", "rdv_pris") else current_statut
                else:
                    new_statut = "repondu" if current_statut not in ("opt_out", "rdv_pris", "interesse") else current_statut
                await db.prospects.update_one(
                    {"id": p["id"]},
                    {"$set": {"statut": new_statut, "reply_action": action},
                     "$push": {"historique": {
                         "type": "reponse_email", "action": action, "date": m["date"] or now,
                         "objet": m["subject"][:200], "extrait": m["body_excerpt"][:300],
                         "source": "imap"}}},
                )
                summary["linked"] += 1
                summary["prospects_updated"] += 1
            else:
                summary["orphans"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Inbox sync : erreur sur %s (%s)", m.get("from_email"), exc)

    try:
        await dump_db(db)
    except Exception:
        pass

    return summary


# ============================================================ Sauvegarde / restauration

@api_router.get("/backup/status")
async def api_backup_status():
    return await backup_status(db)


@api_router.post("/backup/dump")
async def api_backup_dump():
    """Exporte immédiatement la base vers /app/data/backup (fichiers JSON)."""
    return await dump_db(db)


@api_router.post("/backup/restore")
async def api_backup_restore(drop_existing: bool = True):
    """Restaure la base depuis /app/data/backup. Par défaut, écrase les collections."""
    return await restore_db(db, drop_existing=drop_existing)


# ============================================================ App setup

@api_router.post("/admin/migrate-vendabilite")
async def api_migrate_vendabilite():
    """Force le recalcul du score de vendabilité sur tous les prospects."""
    total = 0
    async for p in db.prospects.find({}, {"_id": 0}):
        v = compute_site_vendabilite(p)
        await db.prospects.update_one({"id": p["id"]}, {"$set": v})
        total += 1
    return {"migrated": total}


api_router.include_router(create_webhook_router(db))
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


async def migrate_canal_unique():
    """Migration one-shot : canal unique par prospect (email > whatsapp > linkedin).

    - Remplace les scénarios par les nouveaux templates neutres (sans canal par étape).
    - Supprime les prospects sans aucun moyen de contact.
    - Affecte canal_contact à tous les prospects restants.
    """
    s = await db.settings.find_one({"_id": "global"}) or {}
    if s.get("migration_canal_unique"):
        return
    for profil, sc in DEFAULT_SCENARIOS.items():
        await db.scenarios.replace_one({"profil": profil}, {**sc}, upsert=True)
    vide = {"$not": {"$regex": r"\S"}}
    res = await db.prospects.delete_many(
        {"email": vide, "telephone": vide, "linkedin_url": vide})
    await db.prospects.update_many(
        {"email": {"$regex": r"\S"}}, {"$set": {"canal_contact": "email"}})
    await db.prospects.update_many(
        {"email": vide, "telephone": {"$regex": r"\S"}}, {"$set": {"canal_contact": "whatsapp"}})
    await db.prospects.update_many(
        {"email": vide, "telephone": vide, "linkedin_url": {"$regex": r"\S"}},
        {"$set": {"canal_contact": "linkedin"}})
    await db.settings.update_one(
        {"_id": "global"}, {"$set": {"migration_canal_unique": True}}, upsert=True)
    logger.info(f"Migration canal unique : {res.deleted_count} prospect(s) sans contact supprimé(s)")


async def migrate_scoring_v2():
    """Rescoring one-shot : le profil « site ancien » pèse désormais plus que « pas de site »."""
    s = await db.settings.find_one({"_id": "global"}) or {}
    if s.get("migration_scoring_v2"):
        return
    n = 0
    async for p in db.prospects.find({}, {"_id": 0}):
        score, niveau = compute_score(p)
        if score != int(p.get("score_conversion", 0) or 0):
            await db.prospects.update_one(
                {"id": p["id"]}, {"$set": {"score_conversion": score, "niveau_conversion": niveau}})
            n += 1
    await db.settings.update_one(
        {"_id": "global"}, {"$set": {"migration_scoring_v2": True}}, upsert=True)
    logger.info(f"Migration scoring v2 : {n} prospect(s) rescoré(s)")


async def migrate_vendabilite():
    """Calcule vendabilité sur tous les prospects qui n'ont pas encore ce champ."""
    n = 0
    async for p in db.prospects.find({"score_vendabilite": {"$exists": False}}, {"_id": 0}):
        v = compute_site_vendabilite(p)
        await db.prospects.update_one({"id": p["id"]}, {"$set": v})
        n += 1
    if n:
        logger.info(f"Migration vendabilité : {n} prospect(s) mis à jour")


async def migrate_multicanal():
    """Plan de canaux + variante A/B des objets (idempotente).

    - Prospects sans plan_canaux / variante_ab : champs ajoutés.
    - Prospects avec un ancien plan multi-canal (rotation) : recalcul en plan
      mono-canal (décision utilisateur : toute la séquence sur le même canal).
    """
    n = 0
    query = {"$or": [
        {"plan_canaux": {"$exists": False}},
        {"variante_ab": {"$exists": False}},
        # ancien plan avec rotation de canaux → à réaligner en mono-canal
        {"$expr": {"$gt": [{"$size": {"$setUnion": [{"$ifNull": ["$plan_canaux", []]}, []]}}, 1]}},
    ]}
    async for p in db.prospects.find(query, {"_id": 0}):
        updates: dict = {}
        if "variante_ab" not in p:
            updates["variante_ab"] = random.choice(["A", "B"])
        plan = canal_plan(p)
        if plan != p.get("plan_canaux"):
            updates["plan_canaux"] = plan
        if plan and p.get("statut") == "a_contacter" and p.get("canal_contact") != plan[0]:
            updates["canal_contact"] = plan[0]
        if updates:
            await db.prospects.update_one({"id": p["id"]}, {"$set": updates})
            n += 1
    if n:
        logger.info(f"Migration plan de canaux : {n} prospect(s) mis à jour")



@app.on_event("startup")
async def seed():
    for profil, sc in DEFAULT_SCENARIOS.items():
        existing = await db.scenarios.find_one({"profil": profil})
        if not existing:
            await db.scenarios.insert_one({**sc})
        elif int(existing.get("version", 1) or 1) < int(sc.get("version", 1)):
            # Templates par défaut mis à jour → on remplace l'ancienne version
            await db.scenarios.replace_one({"profil": profil}, {**sc})
    await migrate_canal_unique()
    await migrate_scoring_v2()
    if not await db.settings.find_one({"_id": "global"}):
        await db.settings.insert_one({"_id": "global", "prenom_expediteur": "Simon",
                                      "lien_rdv": "", "serper_api_key": ""})
    s = await db.settings.find_one({"_id": "global"})
    if not s.get("webhook_token"):
        await db.settings.update_one({"_id": "global"},
                                     {"$set": {"webhook_token": uuid.uuid4().hex}})
    await db.prospects.create_index("id", unique=True)
    await db.prospects.create_index([("statut", 1), ("date_prochaine_action", 1)])
    await db.email_log.create_index([("date", -1)])
    # Restauration automatique depuis le backup JSON si la base est vide
    # (cas d'un pod K8s recréé : Mongo local wipé mais /app/data/backup conservé via Git).
    try:
        await restore_if_empty(db)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Restauration auto échouée : %s", exc)
    # Calcul vendabilité après restauration éventuelle (prospects restaurés inclus)
    await migrate_vendabilite()
    await migrate_multicanal()
    asyncio.create_task(autopilot_loop(db))
    asyncio.create_task(backup_loop(db))


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
