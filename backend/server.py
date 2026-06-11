"""API Cockpit de Prospection — scraper + file du jour + séquences."""
from __future__ import annotations

import asyncio
import io
import logging
import os
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
    advance_updates, determine_canal, determine_profil, render_message,
)
from scraper_core import (
    METIERS, USER_AGENT, as_str, audit_site, build_linkedin_link, build_wa_link,
    compute_score, discover_gouv, discover_osm, enrich_phone, has_real_website,
    niveau_from_score, normalize_company_name, normalize_french_phone,
    phone_digits, resolve_site_web, serper_find_site,
)
from autopilot import (
    autopilot_loop, count_sent_today, eligible_prospects, in_window,
    run_tick, send_email_sync,
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
    metier: str
    ville: str
    departement: str = ""
    limite: int = 20
    source: str = "gouv"  # gouv | osm
    auditer: bool = True


class ActionRequest(BaseModel):
    type: str  # envoye | repondu | rdv | skip | opt_out | perdu | gagne | reactiver


class ProspectUpdate(BaseModel):
    telephone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    site_web: Optional[str] = None
    notes: Optional[str] = None
    statut: Optional[str] = None
    message_personnalise: Optional[str] = None
    profil: Optional[str] = None


class AIImproveRequest(BaseModel):
    message: str
    prospect_id: Optional[str] = None
    canal: str = "whatsapp"
    instruction: str = ""


class SettingsUpdate(BaseModel):
    prenom_expediteur: Optional[str] = None
    lien_rdv: Optional[str] = None
    serper_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    email_expediteur: Optional[str] = None
    email_reponse: Optional[str] = None
    autopilot_actif: Optional[bool] = None
    autopilot_quota_jour: Optional[int] = None
    autopilot_heure_debut: Optional[int] = None
    autopilot_heure_fin: Optional[int] = None
    autopilot_jours_ouvres: Optional[bool] = None


class EtapeModel(BaseModel):
    etape: int
    delai_jours: int
    template: str
    objet: str = ""


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
    }
    if not p["score_conversion"]:
        p["score_conversion"], p["niveau_conversion"] = compute_score(p)
    if not p["niveau_conversion"]:
        p["niveau_conversion"] = niveau_from_score(p["score_conversion"])
    p["profil"] = as_str(data.get("profil")) or determine_profil(p)
    p["canal_contact"] = determine_canal(p)
    p["entreprise_norm"] = normalize_company_name(p["entreprise"])
    p["tel_digits"] = phone_digits(p["telephone"])
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
    message = as_str(p.get("message_personnalise")) or render_message(step.get("template", ""), p, settings)
    canal = p.get("canal_contact") or determine_canal(p) or "whatsapp"
    return {
        "prospect": p,
        "etape": step.get("etape", 1),
        "total_etapes": len(etapes),
        "canal": canal,
        "message": message,
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
         "canal_contact": {"$in": ["whatsapp", "linkedin"]}})
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


@api_router.get("/queue")
async def get_queue(limit: int = 50):
    """File du jour : actions manuelles uniquement (WhatsApp / LinkedIn).

    Les prospects au canal email sont gérés par le pilote automatique.
    """
    settings = await get_settings()
    cursor = db.prospects.find(
        {"statut": "a_contacter", "date_prochaine_action": {"$lte": now_iso()},
         "canal_contact": {"$in": ["whatsapp", "linkedin"]}},
        {"_id": 0},
    ).sort("score_conversion", -1).limit(limit)
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
    apercu = [{"etape": e["etape"], "canal": item["canal"], "delai_jours": e["delai_jours"],
               "message": render_message(e["template"], p, settings)} for e in scenario.get("etapes", [])]
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
        if not deja_contacte:  # le canal est figé dès le premier envoi de la séquence
            updates["canal_contact"] = determine_canal({**p, **updates})
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
        updates.update(advance_updates(p, scenario.get("etapes", [])))
    elif action == "skip":
        updates["date_prochaine_action"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif action in ("repondu", "rdv", "gagne", "perdu", "opt_out"):
        updates["statut"] = action
    elif action == "reactiver":
        updates["statut"] = "a_contacter"
        updates["etape_relance"] = 1
        updates["date_prochaine_action"] = now_iso()
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
            await _job_log(job_id, f"Découverte via {params.source} : {params.metier} à {params.ville}…",
                           statut="decouverte", progress=5)
            if params.source == "osm":
                items = await discover_osm(http, params.metier, params.ville, limite=params.limite)
            else:
                items = await discover_gouv(http, params.metier, params.ville, params.departement, params.limite)
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
                        if params.auditer:
                            if has_real_website(item.get("site_web", "")) and not item.get("telephone"):
                                item["telephone"] = await enrich_phone(http, item["site_web"])
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
           "etapes": [e.model_dump() for e in body.etapes]}
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
        "auto": False, "statut": "envoye", "date": now_iso()})
    await db.prospects.update_one(
        {"id": body.prospect_id},
        {"$push": {"historique": {"type": "email_envoye", "date": now_iso(),
                                  "etape": p.get("etape_relance", 1)}}})
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
            "serper_api_key": s.get("serper_api_key", ""),
            "sendgrid_api_key": s.get("sendgrid_api_key", ""),
            "email_expediteur": s.get("email_expediteur", ""),
            "email_reponse": s.get("email_reponse", ""),
            "webhook_token": s.get("webhook_token", ""),
            "autopilot_actif": bool(s.get("autopilot_actif", False)),
            "autopilot_quota_jour": int(s.get("autopilot_quota_jour", 50) or 50),
            "autopilot_heure_debut": int(s.get("autopilot_heure_debut", 9) or 0),
            "autopilot_heure_fin": int(s.get("autopilot_heure_fin", 18) or 24),
            "autopilot_jours_ouvres": bool(s.get("autopilot_jours_ouvres", True))}


@api_router.put("/settings")
async def write_settings(body: SettingsUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.settings.update_one({"_id": "global"}, {"$set": updates}, upsert=True)
    return await read_settings()


# ============================================================ App setup

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


@app.on_event("startup")
async def seed():
    for profil, sc in DEFAULT_SCENARIOS.items():
        existing = await db.scenarios.find_one({"profil": profil})
        if not existing:
            await db.scenarios.insert_one({**sc})
    await migrate_canal_unique()
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
    asyncio.create_task(autopilot_loop(db))


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
