"""Coeur du scraper porté depuis Scraper2UI : sources, enrichissement, audit, scoring."""
from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urlparse, quote
from html import unescape

import httpx
import phonenumbers
from bs4 import BeautifulSoup
from phonenumbers import NumberParseException, PhoneNumberFormat

PAS_DE_SITE = "Pas de site"
USER_AGENT = "ProspectionArtisansFR/1.0"

# ---------------------------------------------------------------- utils

def as_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


PHONE_PATTERN = re.compile(r"(?:(?:\+|00)\s*33|0)\s*[1-9](?:[\s.\-]*\d{2}){4}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def normalize_url(url: str) -> str:
    url = as_str(url)
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/")


def normalize_french_phone(raw: str) -> str:
    raw = re.sub(r"[^\d+]", "", as_str(raw))
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if raw.startswith("0") and len(raw) == 10:
        raw = "+33" + raw[1:]
    try:
        num = phonenumbers.parse(raw, "FR")
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL)
    except NumberParseException:
        pass
    return raw.strip()


def phone_digits(phone: str) -> str:
    p = normalize_french_phone(phone)
    return re.sub(r"\D", "", p)[-9:] if p else ""


def extract_phones_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in PHONE_PATTERN.findall(text or ""):
        n = normalize_french_phone(match)
        if n and n not in found:
            found.append(n)
    return found


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().strip()


LEGAL_FORMS = re.compile(r"\b(sarl|sas|sasu|eurl|sa|sci|snc|scop|ltd|llc|inc)\b", re.I)


def normalize_company_name(name: str) -> str:
    n = fold(name)
    n = LEGAL_FORMS.sub("", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return " ".join(n.split())


# ---------------------------------------------------------------- filtres annuaires

DIRECTORY_DOMAINS = (
    "facebook.com", "fb.com", "linkedin.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "pagesjaunes.fr", "societe.com", "societe-info.com",
    "infogreffe", "pappers.fr", "manageo.fr", "verif.com", "data.gouv.fr",
    "annuaire-entreprises", "wikipedia.org", "google.com", "google.fr", "bing.com",
    "lefigaro.fr", "figaro.fr", "ouest-france.fr", "kompass.com", "europages",
    "118000.fr", "118712.fr", "hoodspot", "cylex.fr", "hotfrog.fr", "infobel.fr",
    "yelp.", "tripadvisor.", "mappy.com", "petitfute.com", "linternaute.com",
    "bottin.fr", "amazon.", "ebay.", "meilleur-artisan", "starofservice", "travaux.com",
    "hellopro.fr", "houzz.", "prontopro.fr", "allovoisins", "plus-que-pro", "quotatis",
    "travauxlib", "devis-travaux", "needhelp", "societe.net", "11880.com", "score3.fr",
)

DIRECTORY_PATH_FRAGMENTS = (
    "/entreprise/", "/entreprises/", "/societe/", "/societes/", "/fiche-", "/annuaire/",
    "/profil/", "/company/", "/etablissement/", "/business/", "/recherche/", "/siren",
    "/siret", "/professionnel/", "/artisan/",
)

_NO_SITE_ALIASES = frozenset({"", "pas de site", "aucun", "n/a", "na", "none", "null", "-", "non"})


def is_annuaire_url(url: str) -> bool:
    if not url:
        return True
    try:
        parsed = urlparse(url.strip().lower())
    except ValueError:
        return True
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return True
    if any(d in host for d in DIRECTORY_DOMAINS):
        return True
    path = (parsed.path or "").lower()
    return any(f in path for f in DIRECTORY_PATH_FRAGMENTS)


def has_real_website(site_web: str) -> bool:
    s = as_str(site_web).lower()
    return s not in _NO_SITE_ALIASES and as_str(site_web) != PAS_DE_SITE


def resolve_site_web(url: str) -> str:
    raw = as_str(url)
    if raw.lower() in _NO_SITE_ALIASES or raw == PAS_DE_SITE:
        return PAS_DE_SITE
    normalized = normalize_url(raw)
    if not normalized or is_annuaire_url(normalized):
        return PAS_DE_SITE
    return normalized


# ---------------------------------------------------------------- source gouv

GOUV_API = "https://recherche-entreprises.api.gouv.fr/search"

METIER_NAF: dict[str, list[str]] = {
    "plombier": ["43.22A", "43.22B", "43.22Z", "43.29A", "43.29B", "43.21A", "43.21B"],
    "electricien": ["43.21A", "43.21B"],
    "menuisier": ["43.32A", "43.32B", "16.23Z", "43.32C"],
    "peintre": ["43.34Z", "43.34A", "43.34B"],
    "maçon": ["43.99C", "43.91Z", "43.99A", "43.99B", "43.99D", "43.99E"],
    "macon": ["43.99C", "43.91Z", "43.99A", "43.99B", "43.99D", "43.99E"],
    "couvreur": ["43.91Z", "43.91A", "43.91B"],
    "chauffagiste": ["43.22B", "43.21A", "43.22Z", "43.29A", "43.22A"],
    "serrurier": ["43.32B", "25.99Z", "25.72Z"],
    "carreleur": ["43.33Z"],
    "jardinier": ["81.30Z", "81.10Z", "01.30Z"],
}

METIERS = list(METIER_NAF.keys())


async def discover_gouv(http: httpx.AsyncClient, metier: str, ville: str,
                        departement: str = "", limite: int = 30) -> list[dict]:
    naf_codes = METIER_NAF.get(as_str(metier).lower())
    results: list[dict] = []
    seen: set[str] = set()

    async def fetch_pages(codes):
        out = []
        for page in range(1, 9):
            params = {"q": f"{metier} {ville}".strip(), "per_page": 25, "page": page}
            if departement:
                dep = as_str(departement)
                params["departement"] = dep.zfill(2) if len(dep) <= 2 else dep
            if codes:
                params["code_naf"] = ",".join(codes)
            try:
                resp = await http.get(GOUV_API, params=params)
                resp.raise_for_status()
                items = resp.json().get("results") or []
            except httpx.HTTPError:
                break
            if not items:
                break
            out.extend(items)
            if len(out) >= limite * 2 or len(items) < 25:
                break
        return out

    raw = await fetch_pages(naf_codes)
    if naf_codes and len(raw) < limite:
        raw += await fetch_pages(None)

    for item in raw:
        siren = as_str(item.get("siren"))
        nom = as_str(item.get("nom_complet") or item.get("nom_raison_sociale") or "Sans nom")
        key = siren or normalize_company_name(nom)
        if key in seen:
            continue
        seen.add(key)
        siege = item.get("siege") or {}
        results.append({
            "entreprise": nom,
            "metier": metier,
            "adresse": as_str(siege.get("adresse") or siege.get("geo_adresse") or ""),
            "ville": as_str(siege.get("libelle_commune", "")) or ville,
            "code_postal": as_str(siege.get("code_postal", "")),
            "siren": siren,
            "telephone": "",
            "site_web": "",
            "source": "API Entreprises (gouv.fr)",
        })
        if len(results) >= limite:
            break
    return results


# ---------------------------------------------------------------- source OSM

OSM_CRAFT = {
    "plombier": ('["craft"="plumber"]',),
    "electricien": ('["craft"="electrician"]',),
    "menuisier": ('["craft"="carpenter"]', '["craft"="joiner"]'),
    "peintre": ('["craft"="painter"]',),
    "maçon": ('["craft"="builder"]', '["craft"="bricklayer"]'),
    "macon": ('["craft"="builder"]', '["craft"="bricklayer"]'),
    "couvreur": ('["craft"="roofer"]',),
    "chauffagiste": ('["craft"="hvac"]', '["craft"="heating_engineer"]'),
    "serrurier": ('["craft"="locksmith"]', '["craft"="metal_construction"]'),
    "carreleur": ('["craft"="tiler"]',),
    "jardinier": ('["craft"="gardener"]', '["shop"="garden_centre"]'),
}


# Miroirs Overpass, essayés dans l'ordre (le 1er peut être bloqué selon le réseau)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


async def discover_osm(http: httpx.AsyncClient, metier: str, ville: str,
                       rayon_km: int = 15, limite: int = 30) -> list[dict]:
    # Géocodage Nominatim
    geo = await http.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{ville}, France", "format": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT},
    )
    geo.raise_for_status()
    places = geo.json()
    if not places:
        return []
    lat, lon = places[0]["lat"], places[0]["lon"]

    filters = OSM_CRAFT.get(as_str(metier).lower(), (f'["craft"="{fold(metier)}"]',))
    radius = rayon_km * 1000
    parts = []
    for f in filters:
        parts.append(f'node{f}(around:{radius},{lat},{lon});')
        parts.append(f'way{f}(around:{radius},{lat},{lon});')
    query = f"[out:json][timeout:60];({''.join(parts)});out center tags {limite * 3};"

    # Plusieurs serveurs Overpass : bascule automatique si l'un est injoignable
    resp = None
    last_err: Exception | None = None
    for url in OVERPASS_ENDPOINTS:
        try:
            resp = await http.post(url, data={"data": query}, timeout=90)
            resp.raise_for_status()
            break
        except httpx.HTTPError as e:
            last_err = e
            resp = None
    if resp is None:
        raise RuntimeError(f"Serveurs Overpass (OSM) injoignables : {last_err}")
    elements = resp.json().get("elements", [])

    results, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        nom = as_str(tags.get("name"))
        if not nom:
            continue
        key = normalize_company_name(nom)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "entreprise": nom,
            "metier": metier,
            "adresse": " ".join(filter(None, [as_str(tags.get("addr:housenumber")), as_str(tags.get("addr:street"))])),
            "ville": as_str(tags.get("addr:city")) or ville,
            "code_postal": as_str(tags.get("addr:postcode")),
            "siren": "",
            "telephone": normalize_french_phone(tags.get("phone") or tags.get("contact:phone") or ""),
            "site_web": resolve_site_web(tags.get("website") or tags.get("contact:website") or ""),
            "email": as_str(tags.get("email") or tags.get("contact:email")),
            "source": "OpenStreetMap",
        })
        if len(results) >= limite:
            break
    return results


# ---------------------------------------------------------------- Serper (optionnel)

async def serper_find_site(http: httpx.AsyncClient, api_key: str, nom: str, ville: str, metier: str) -> str:
    """Cherche le site web via Google (Serper). Retourne URL ou PAS_DE_SITE."""
    try:
        resp = await http.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": f'"{nom}" {ville} {metier}', "gl": "fr", "hl": "fr", "num": 6},
        )
        resp.raise_for_status()
        organic = resp.json().get("organic", [])
    except httpx.HTTPError:
        return PAS_DE_SITE
    nom_norm = normalize_company_name(nom)
    tokens = [t for t in nom_norm.split() if len(t) > 3]
    for item in organic:
        url = resolve_site_web(item.get("link", ""))
        if not has_real_website(url):
            continue
        blob = fold(item.get("title", "") + " " + item.get("snippet", "") + " " + url)
        if tokens and not any(t in blob for t in tokens):
            continue
        return url
    return PAS_DE_SITE


# ---------------------------------------------------------------- enrichissement téléphone

CONTACT_PATHS = ["/contact", "/contactez-nous", "/nous-contacter", "/mentions-legales"]


async def enrich_phone(http: httpx.AsyncClient, site_web: str) -> str:
    if not has_real_website(site_web):
        return ""
    urls = [site_web] + [site_web.rstrip("/") + p for p in CONTACT_PATHS]
    for url in urls:
        try:
            resp = await http.get(url, follow_redirects=True)
            if resp.status_code >= 400:
                continue
        except httpx.HTTPError:
            continue
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            if a["href"].startswith("tel:"):
                p = normalize_french_phone(a["href"][4:])
                if p:
                    return p
        phones = extract_phones_from_text(soup.get_text(" ", strip=True))
        if phones:
            return phones[0]
    return ""


def is_mobile_fr(tel: str) -> bool:
    """True si le numéro est un mobile français (06/07) — seul type joignable sur WhatsApp."""
    raw = as_str(tel)
    if not raw:
        return False
    try:
        num = phonenumbers.parse(raw, "FR")
    except NumberParseException:
        return False
    return phonenumbers.number_type(num) in (
        phonenumbers.PhoneNumberType.MOBILE,
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
    )


BAD_EMAIL_PARTS = (
    "example", "exemple", "sentry", "wixpress", "@domain", "email.com", "votre",
    "prenom", "wordpress", "schema.org", "u003e", "%20", "..", "@2x", "no-reply", "noreply",
)
ASSET_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                    ".css", ".js", ".woff", ".woff2", ".ico", ".pdf")


def _extract_emails(html_text: str) -> list[str]:
    out: list[str] = []
    for raw in EMAIL_PATTERN.findall(unescape(html_text)):
        e = raw.strip().strip(".").lower()
        if any(b in e for b in BAD_EMAIL_PARTS) or e.endswith(ASSET_EXTENSIONS):
            continue
        if e not in out:
            out.append(e)
    return out


async def enrich_email(http: httpx.AsyncClient, site_web: str) -> str:
    """Cherche un email sur le site : accueil puis pages contact / mentions légales.

    Privilégie un email du même domaine que le site (contact@domaine.fr…).
    """
    if not has_real_website(site_web):
        return ""
    domain = re.sub(r"^www\.", "", urlparse(site_web).netloc).lower()
    urls = [site_web] + [site_web.rstrip("/") + p for p in CONTACT_PATHS]
    found: list[str] = []
    for url in urls:
        try:
            resp = await http.get(url, follow_redirects=True)
            if resp.status_code >= 400:
                continue
        except httpx.HTTPError:
            continue
        for e in _extract_emails(resp.text):
            if e not in found:
                found.append(e)
        if any(e.split("@")[-1] == domain for e in found):
            break
    for e in found:
        if e.split("@")[-1] == domain:
            return e
    return found[0] if found else ""


# ---------------------------------------------------------------- audit site + signaux

def _detect_buying_signals(text_lower: str, site_web: str, telephone: str) -> tuple[str, str]:
    signals: dict[str, bool] = {}
    has_site = has_real_website(site_web)
    signals["site_en_construction"] = any(
        k in text_lower for k in ("site en construction", "coming soon", "en construction", "bientôt disponible"))
    years = [int(m) for m in re.findall(r"\b(20[12]\d)\b", text_lower) if 2010 <= int(m) <= 2030]
    max_year = max(years) if years else 0
    signals["copyright_obsolete"] = 0 < max_year < 2025
    signals["pas_de_site"] = not has_site
    signals["pas_de_telephone"] = bool(
        has_site and telephone and telephone.replace(" ", "")[-9:] not in text_lower.replace(" ", ""))
    signals["pas_de_contact"] = has_site and not any(
        k in text_lower for k in ("contact", "devis", "demande", "formulaire"))
    signals["devis_gratuit"] = any(
        k in text_lower for k in ("devis gratuit", "devis offert", "devis sans engagement", "devis en ligne"))
    signals["blog_inactif"] = has_site and any(
        k in text_lower for k in ("blog", "actualités", "actualites", "news")) and max_year < 2024
    signals["entreprise_etablie"] = any(
        k in text_lower for k in ("depuis plus de", "créé en", "créée en", "ans d'expérience"))
    signals["contenu_limite"] = has_site and len(text_lower) < 800

    principal = ""
    priorities = [
        ("pas_de_site", "Pas de site web"),
        ("site_en_construction", "Site en construction"),
        ("copyright_obsolete", "Copyright obsolète"),
        ("pas_de_telephone", "Téléphone manquant"),
        ("pas_de_contact", "Pas de formulaire de contact"),
        ("devis_gratuit", "Propose des devis gratuits"),
        ("blog_inactif", "Blog inactif"),
        ("contenu_limite", "Contenu très limité"),
        ("entreprise_etablie", "Entreprise établie"),
    ]
    for key, label in priorities:
        if signals.get(key):
            principal = label
            break
    return json.dumps(signals, ensure_ascii=False), principal


def qualite_from_note(note: int, has_site: bool) -> str:
    if not has_site:
        return "Sans site"
    if note < 50:
        return "Ancien / obsolète"
    if note < 80:
        return "Moyen"
    return "Moderne"


async def audit_site(http: httpx.AsyncClient, site_web: str, telephone: str, metier: str) -> dict:
    """Audit /100 + pistes + signaux d'achat. Retourne dict de champs prospect."""
    site_web = resolve_site_web(site_web)
    out = {"site_web": site_web, "note_site": 0, "qualite_site": "Sans site",
           "opportunites": "", "signaux_conversion": "", "signal_principal": ""}

    if not has_real_website(site_web):
        out["opportunites"] = ("Pas de site web — créer un site vitrine avec métier, "
                               "zone d'intervention, téléphone cliquable et formulaire de contact.")
        out["signaux_conversion"], out["signal_principal"] = _detect_buying_signals("", site_web, telephone)
        return out

    try:
        resp = await http.get(site_web, follow_redirects=True)
    except httpx.HTTPError:
        out.update(note_site=10, qualite_site="Ancien / obsolète",
                   opportunites="Site inaccessible ou trop lent — vérifier hébergement, HTTPS et disponibilité.")
        out["signaux_conversion"], out["signal_principal"] = _detect_buying_signals("", site_web, telephone)
        return out

    if resp.status_code >= 400:
        out.update(note_site=15, qualite_site="Ancien / obsolète",
                   opportunites=f"Erreur HTTP {resp.status_code} — corriger la page d'accueil ou les redirections.")
        out["signaux_conversion"], out["signal_principal"] = _detect_buying_signals("", site_web, telephone)
        return out

    final_url = str(resp.url)
    if is_annuaire_url(final_url):
        out["site_web"] = PAS_DE_SITE
        out["opportunites"] = "Pas de site web (fiche annuaire exclue) — créer un site vitrine dédié."
        out["signaux_conversion"], out["signal_principal"] = _detect_buying_signals("", PAS_DE_SITE, telephone)
        return out

    out["site_web"] = resolve_site_web(final_url)
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    text_lower = soup.get_text(" ", strip=True).lower()

    score = 0
    pistes: list[str] = []

    if final_url.startswith("https://"):
        score += 15
    else:
        pistes.append("Passer le site en HTTPS (certificat SSL).")

    title = soup.find("title")
    if title and len(title.get_text(strip=True)) >= 10:
        score += 10
        if metier and metier.lower() not in title.get_text(strip=True).lower():
            pistes.append(f"Inclure le métier « {metier} » et la ville dans la balise <title> (SEO local).")
    else:
        pistes.append("Ajouter une balise <title> descriptive (métier + ville + nom).")

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and as_str(meta_desc.get("content", "")):
        score += 10
    else:
        pistes.append("Ajouter une meta description pour Google.")

    if soup.find("meta", attrs={"name": "viewport"}):
        score += 15
    else:
        pistes.append("Rendre le site responsive (mobile) — balise viewport manquante.")

    if soup.find_all("h1"):
        score += 10
    else:
        pistes.append("Ajouter un titre H1 clair sur la page d'accueil.")

    phone_visible = bool(telephone and telephone.replace(" ", "")[-9:] in text_lower.replace(" ", ""))
    if phone_visible:
        score += 15
    else:
        pistes.append("Afficher le téléphone en évidence avec un lien cliquable tel:.")

    if any(k in text_lower for k in ("contact", "devis", "demande", "formulaire")):
        score += 10
    else:
        pistes.append("Ajouter une section Contact / Devis gratuit.")

    imgs = soup.find_all("img")
    if imgs and len([i for i in imgs if not as_str(i.get("alt", ""))]) / max(len(imgs), 1) < 0.5:
        score += 5

    if any(k in text_lower for k in ("rgpd", "données personnelles", "politique de confidentialité")):
        score += 5
    else:
        pistes.append("Ajouter une mention RGPD / politique de confidentialité.")

    if soup.find("meta", property="og:title") or soup.find("meta", attrs={"property": "og:image"}):
        score += 5
    else:
        pistes.append("Configurer les balises Open Graph (partage réseaux sociaux).")

    if len(html) > 500:
        score += 10
    else:
        pistes.append("Enrichir le contenu de la page d'accueil.")

    out["note_site"] = min(score, 100)
    out["qualite_site"] = qualite_from_note(out["note_site"], True)
    out["opportunites"] = " | ".join(pistes) if pistes else "Site correct mais perfectible — refonte, vitesse, avis Google."
    out["signaux_conversion"], out["signal_principal"] = _detect_buying_signals(text_lower, out["site_web"], telephone)
    return out


# ---------------------------------------------------------------- scoring conversion

POIDS_ABSENCE_SITE, POIDS_JOIGNABLE, POIDS_EMAIL, POIDS_SIGNAUX, POIDS_WHATSAPP, POIDS_RATING = 25, 15, 15, 25, 10, 10

SIGNAL_POIDS = {
    "pas_de_site": 0.30, "site_en_construction": 0.20, "copyright_obsolete": 0.15,
    "pas_de_telephone": 0.10, "pas_de_contact": 0.10, "devis_gratuit": 0.05,
    "blog_inactif": 0.05, "contenu_limite": 0.05,
}


def niveau_from_score(score: int) -> str:
    if score >= 80:
        return "Très chaud"
    if score >= 60:
        return "Chaud"
    if score >= 30:
        return "Tiède"
    return "Froid"


def compute_score(p: dict) -> tuple[int, str]:
    score = 0
    site = p.get("site_web", "")
    note = int(p.get("note_site", 0) or 0)
    if not has_real_website(site):
        score += POIDS_ABSENCE_SITE
    elif note < 50:
        score += POIDS_ABSENCE_SITE
    elif note < 70:
        score += POIDS_ABSENCE_SITE // 2

    if p.get("telephone"):
        score += POIDS_JOIGNABLE
    if p.get("email"):
        score += POIDS_EMAIL // 2

    try:
        signaux = json.loads(p.get("signaux_conversion") or "{}")
    except (json.JSONDecodeError, TypeError):
        signaux = {}
    sig_score = sum(w * POIDS_SIGNAUX for k, w in SIGNAL_POIDS.items() if signaux.get(k))
    score += int(sig_score)

    tel = p.get("telephone", "")
    if tel:
        try:
            num = phonenumbers.parse(tel, "FR")
            if phonenumbers.is_valid_number(num) and phonenumbers.number_type(num) == phonenumbers.PhoneNumberType.MOBILE:
                score += POIDS_WHATSAPP
            else:
                score += POIDS_WHATSAPP // 2
        except NumberParseException:
            score += POIDS_WHATSAPP // 2

    rating = float(p.get("rating", 0) or 0)
    if rating >= 4.0:
        score += POIDS_RATING
    elif rating > 0:
        score += POIDS_RATING // 2

    score = min(score, 100)
    return score, niveau_from_score(score)


# ---------------------------------------------------------------- liens

def build_wa_link(telephone: str, message: str = "") -> str:
    if not telephone:
        return ""
    digits = re.sub(r"[^\d]", "", telephone)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "33" + digits[1:]
    if not digits or len(digits) < 10:
        return ""
    link = f"https://web.whatsapp.com/send?phone={digits}"
    if message:
        link += f"&text={quote(message)}"
    return link


def build_linkedin_link(linkedin_url: str, entreprise: str, ville: str = "") -> str:
    if as_str(linkedin_url):
        return as_str(linkedin_url)
    q = quote(f"{entreprise} {ville}".strip())
    return f"https://www.linkedin.com/search/results/all/?keywords={q}"
