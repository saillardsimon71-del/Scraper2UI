"""Scénarios de relance, détermination du profil/canal et rendu des messages."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from scraper_core import as_str, has_real_website, is_mobile_fr

PROFILS = ["pas_de_site", "site_ancien", "signal_chaud", "site_moyen"]

PROFIL_LABELS = {
    "pas_de_site": "Pas de site",
    "site_ancien": "Site ancien",
    "signal_chaud": "Signal chaud",
    "site_moyen": "Site moyen",
}

CANAL_LABELS = {"email": "Email", "whatsapp": "WhatsApp", "linkedin": "LinkedIn", "telephone": "Téléphone"}

# Offre par défaut, surchargée par le champ « offre » des paramètres (variable {offre}).
DEFAULT_OFFRE = "un site pro à partir de 300 €, livré en 72 h, spécialement pensé pour les artisans"

# Version des templates par défaut : incrémentée à chaque refonte des messages.
# Au démarrage, les scénarios en base avec une version inférieure sont remplacés.
SCENARIO_VERSION = 2


def determine_canal(p: dict) -> str:
    """Canal unique de toute la séquence, par priorité :
    email > whatsapp (mobile 06/07) > linkedin > téléphone (appel sur fixe).

    Retourne "" si le prospect n'a aucun moyen de contact (à supprimer / ne pas ajouter).
    """
    if as_str(p.get("email")):
        return "email"
    if is_mobile_fr(p.get("telephone", "")):
        return "whatsapp"
    if as_str(p.get("linkedin_url")):
        return "linkedin"
    if as_str(p.get("telephone")):
        return "telephone"
    return ""


# ---------------------------------------------------------------- saisonnalité

# (mots-clés métier, mois d'envoi pertinents, accroche) — variable {accroche_saison}.
# L'accroche est envoyée AVANT le pic de demande du métier : c'est le moment où
# travailler sa visibilité a le plus d'impact, pendant que les concurrents dorment.
SAISONNALITE = [
    (("couvreur", "toiture", "charpent", "zingu"), {5, 6, 7, 8, 9},
     "D'ailleurs, le gros des demandes toiture arrive à l'automne — c'est maintenant qu'il faut être visible, pendant que vos concurrents ne font rien."),
    (("chauffag", "poele", "poêle", "fumiste", "pompe a chaleur", "pompe à chaleur"), {8, 9, 10, 11},
     "D'ailleurs, les demandes chauffage explosent aux premiers froids — autant être visible avant le rush."),
    (("ramon",), {6, 7, 8, 9},
     "D'ailleurs, la saison du ramonage démarre à l'automne — c'est maintenant que ça se prépare."),
    (("peintre", "peinture"), {12, 1, 2, 3},
     "D'ailleurs, les chantiers peinture repartent au printemps — c'est le bon moment pour préparer votre visibilité."),
    (("paysag", "jardin", "espaces verts", "elagage", "élagage"), {12, 1, 2, 3},
     "D'ailleurs, les demandes jardin repartent dès le printemps — autant être visible avant la saison."),
    (("macon", "maçon", "terrass", "gros oeuvre", "gros œuvre"), {1, 2, 3, 4},
     "D'ailleurs, la saison des chantiers redémarre au printemps — c'est maintenant que les clients comparent les devis."),
    (("climatis", "clim "), {2, 3, 4, 5},
     "D'ailleurs, les demandes de clim explosent aux premières chaleurs — autant être visible avant l'été."),
    (("piscin",), {10, 11, 12, 1, 2},
     "D'ailleurs, les projets piscine se signent en hiver pour l'été — c'est maintenant que ça se joue."),
]


def accroche_saison(metier: str, month: int | None = None) -> str:
    """Accroche saisonnière si le métier a un pic de demande prévisible et qu'on est
    dans la fenêtre d'envoi pertinente. Sinon chaîne vide (retirée du template)."""
    m = (metier or "").lower()
    if not m:
        return ""
    month = month or datetime.now(timezone.utc).month
    for keywords, months, accroche in SAISONNALITE:
        if month in months and any(k in m for k in keywords):
            return accroche
    return ""


def step_template(step: dict, canal: str) -> str:
    """Template adapté au canal : la variante courte (template_court) est utilisée
    sur WhatsApp et LinkedIn — un message long d'un inconnu y est perçu comme du spam.
    L'email garde le template complet."""
    if canal in ("whatsapp", "linkedin") and as_str(step.get("template_court")):
        return step["template_court"]
    return step.get("template", "")


# delai_jours = jours d'attente APRÈS l'étape précédente (étape 1 : immédiat)
# template       : message complet (email, ou fallback tous canaux)
# template_court : variante 2-3 lignes utilisée sur WhatsApp / LinkedIn
# L'objet n'est utilisé que pour le canal email.
DEFAULT_SCENARIOS = {
    "pas_de_site": {
        "profil": "pas_de_site",
        "label": "Pas de site",
        "description": "Prospect sans aucun site web. Attention : il a souvent survécu des années au bouche-à-oreille — la douleur est faible. Angle fiche Google (moins intimidant) + recherche locale concrète.",
        "version": SCENARIO_VERSION,
        "etapes": [
            {"etape": 1, "delai_jours": 0,
             "objet": "Un site pour {entreprise} ?",
             "template": "Bonjour, je suis {prenom_exp}, je travaille dans le web. Je cherchais le site de {entreprise} pour voir vos réalisations, mais je n'ai rien trouvé en ligne. Vous avez une page quelque part ?",
             "template_court": ""},
            {"etape": 2, "delai_jours": 3,
             "objet": "Recherche « {metier} {ville} » sur Google",
             "template": "Bonjour, c'est {prenom_exp}. J'ai cherché « {metier} {ville} » sur Google : vos concurrents ressortent, pas {entreprise}. Bonne nouvelle : même sans site, une fiche Google bien remplie (photos de chantiers, avis, horaires) peut déjà vous amener des appels. {accroche_saison} Je vous montre ce que ça donnerait pour vous ?",
             "template_court": "Bonjour, c'est {prenom_exp}. J'ai cherché « {metier} {ville} » sur Google : vos concurrents ressortent, pas {entreprise}. Une fiche Google bien remplie suffit déjà à récupérer des appels — je vous montre ?"},
            {"etape": 3, "delai_jours": 4,
             "objet": "Une idée de site pour {entreprise}",
             "template": "Bonjour, c'est encore {prenom_exp}. J'ai préparé une idée de site pour {entreprise} — simple, pensé pour récupérer des demandes de devis : {offre}. Vous m'envoyez 5 photos de chantiers, je m'occupe du reste. Je vous l'envoie ? {lien_rdv}",
             "template_court": "Bonjour, {prenom_exp} à nouveau. J'ai préparé une idée de site pour {entreprise} ({offre}). Je vous l'envoie ? {lien_rdv}"},
            {"etape": 4, "delai_jours": 3,
             "objet": "Dernier message — {entreprise} sur Google",
             "template": "Bonjour,\n\nDernier message de ma part, promis.\n\nJe n'ai trouvé ni site ni fiche Google complète pour {entreprise}. Concrètement : quand quelqu'un cherche « {metier} {ville} », il appelle ceux qu'il trouve — pas vous.\n\nC'est exactement ce que je règle pour les artisans : {offre}.\n\nSi le timing est mauvais, dites-le moi simplement. Sinon, 15 minutes suffisent : {lien_rdv}\n\nBonne journée,\n{prenom_exp}",
             "template_court": "Bonjour, dernier message promis. Si le timing est mauvais, dites-le moi simplement. Sinon : {lien_rdv}"},
        ],
    },
    "site_ancien": {
        "profil": "site_ancien",
        "label": "Site ancien",
        "description": "Site existant mais obsolète (note < 50/100). Souvent le prospect le plus chaud : il a déjà investi, il sait que c'est important, et il est frustré que ça ne marche pas.",
        "version": SCENARIO_VERSION,
        "etapes": [
            {"etape": 1, "delai_jours": 0,
             "objet": "Le site de {entreprise} mérite un coup de jeune",
             "template": "Bonjour, je suis {prenom_exp}, je crée des sites pour les artisans. Je suis passé sur {site_web} — beau métier ! Par contre le site mériterait un coup de jeune ({signal}). Ça vous dirait qu'on en parle 2 minutes ?",
             "template_court": ""},
            {"etape": 2, "delai_jours": 3,
             "objet": "Le site de {entreprise} : note {note_site}/100",
             "template": "Bonjour, c'est {prenom_exp}. J'ai analysé le site de {entreprise} : note {note_site}/100. Le vrai problème : quand un client compare « {metier} {ville} » sur Google, un site daté fait fuir en 10 secondes — il appelle le concurrent au site propre. Quelques améliorations simples changeraient la donne. Je vous envoie le détail ?",
             "template_court": "Bonjour, c'est {prenom_exp}. J'ai analysé {site_web} : note {note_site}/100. Un client qui compare sur Google part en 10 secondes sur un site daté. Je vous envoie le détail des points à corriger ?"},
            {"etape": 3, "delai_jours": 4,
             "objet": "Refaire {site_web} : simple et rapide",
             "template": "Bonjour, {prenom_exp} à nouveau. Remettre {site_web} au niveau, c'est plus simple que vous ne pensez : {offre}. {accroche_saison} J'ai déjà noté 2-3 améliorations concrètes pour augmenter vos appels entrants. On en parle ? {lien_rdv}",
             "template_court": "Bonjour, {prenom_exp} à nouveau. Remettre {site_web} au niveau : {offre}. J'ai déjà 2-3 pistes concrètes pour vous. On en parle ? {lien_rdv}"},
            {"etape": 4, "delai_jours": 3,
             "objet": "Dernier message — les pistes pour {entreprise}",
             "template": "Bonjour,\n\nDernier message de ma part, promis.\n\nJ'ai analysé {site_web} et voici l'essentiel : {signal}. Vous avez déjà fait le plus dur en ayant un site — il manque juste ce qui transforme les visites en demandes de devis.\n\nC'est exactement ce que je fais pour les artisans : {offre}.\n\nSi le timing est mauvais, dites-le moi simplement. Sinon, 15 minutes suffisent : {lien_rdv}\n\nBonne journée,\n{prenom_exp}",
             "template_court": "Bonjour, dernier message promis. Si le timing est mauvais, dites-le moi simplement. Sinon : {lien_rdv}"},
        ],
    },
    "signal_chaud": {
        "profil": "signal_chaud",
        "label": "Signal chaud",
        "description": "Fort signal d'achat détecté (score ≥ 80) — séquence rapide.",
        "version": SCENARIO_VERSION,
        "etapes": [
            {"etape": 1, "delai_jours": 0,
             "objet": "{entreprise} : {signal}",
             "template": "Bonjour, je suis {prenom_exp}, je crée des sites pour les artisans. En regardant {entreprise} j'ai remarqué : {signal}. C'est exactement le genre de situation où une présence web propre fait la différence sur les devis. On échange 2 minutes ?",
             "template_court": ""},
            {"etape": 2, "delai_jours": 2,
             "objet": "Les pistes concrètes pour {entreprise}",
             "template": "Bonjour, {prenom_exp} ici. Je reviens vers vous au sujet de {entreprise} ({signal}). J'ai déjà quelques pistes concrètes — et c'est rapide à mettre en place : {offre}. Dispo pour un appel cette semaine ? {lien_rdv}",
             "template_court": "Bonjour, {prenom_exp} ici. Je reviens sur {entreprise} ({signal}). J'ai des pistes concrètes, et c'est rapide : {offre}. Un appel cette semaine ? {lien_rdv}"},
            {"etape": 3, "delai_jours": 3,
             "objet": "On en reste là pour {entreprise} ?",
             "template": "Bonjour, c'est encore {prenom_exp}. L'opportunité est réelle pour {entreprise} : {signal}. {accroche_saison} Si le timing est mauvais, dites-le moi simplement et je ne vous relancerai plus. Sinon, 15 minutes suffisent : {lien_rdv}",
             "template_court": "Bonjour, c'est encore {prenom_exp}. L'opportunité est réelle pour {entreprise} : {signal}. Si le timing est mauvais, dites-le moi et j'arrête là. Sinon : {lien_rdv}"},
            {"etape": 4, "delai_jours": 2,
             "objet": "Dernier message — {entreprise}",
             "template": "Bonjour,\n\nDernier message de ma part, promis. Je vous ai contacté au sujet de {entreprise} : {signal}.\n\nC'est exactement le genre de moment où une présence web propre fait la différence sur les devis — et c'est rapide : {offre}.\n\nUn créneau de 15 minutes cette semaine ? {lien_rdv}\n\nBonne journée,\n{prenom_exp}",
             "template_court": "Bonjour, dernier message promis. Si le timing est mauvais, dites-le moi simplement. Sinon : {lien_rdv}"},
        ],
    },
    "site_moyen": {
        "profil": "site_moyen",
        "label": "Site moyen",
        "description": "Site correct mais perfectible (note 50-79/100).",
        "version": SCENARIO_VERSION,
        "etapes": [
            {"etape": 1, "delai_jours": 0,
             "objet": "Votre site {site_web} a du potentiel",
             "template": "Bonjour, je suis {prenom_exp}, je crée des sites pour les artisans. J'ai vu votre site {site_web}, il a du potentiel mais quelques points pourraient être améliorés pour attirer plus de clients ({signal}). Vous êtes ouvert à un échange rapide ?",
             "template_court": ""},
            {"etape": 2, "delai_jours": 4,
             "objet": "Audit du site de {entreprise} : note {note_site}/100",
             "template": "Bonjour, {prenom_exp}. J'ai audité le site de {entreprise} (note {note_site}/100) : il y a des gains rapides possibles pour mieux ressortir quand on cherche « {metier} {ville} » sur Google, et transformer plus de visites en demandes de devis. Je partage l'audit complet si ça vous intéresse.",
             "template_court": "Bonjour, {prenom_exp}. J'ai audité le site de {entreprise} : note {note_site}/100, avec des gains rapides possibles côté Google et demandes de devis. Je vous partage l'audit ?"},
            {"etape": 3, "delai_jours": 4,
             "objet": "Les gains rapides pour {site_web}",
             "template": "Bonjour, {prenom_exp} à nouveau. J'ai identifié des gains rapides pour {site_web} côté visibilité Google et demandes de devis — et si une remise à niveau complète vous tente : {offre}. {accroche_saison} Je vous partage le détail, gratuit et sans engagement. {lien_rdv}",
             "template_court": "Bonjour, {prenom_exp} à nouveau. J'ai des gains rapides identifiés pour {site_web} (audit gratuit, sans engagement). Je vous partage le détail ? {lien_rdv}"},
            {"etape": 4, "delai_jours": 3,
             "objet": "Dernier message — l'audit de {site_web}",
             "template": "Bonjour,\n\nDernier message de ma part, promis.\n\nJ'ai audité le site de {entreprise} ({site_web}) : il a du potentiel, et quelques gains rapides sont possibles côté visibilité Google et demandes de devis.\n\nJe vous partage volontiers le détail de l'audit — c'est gratuit et sans engagement.\n\nOn en parle 15 minutes ? {lien_rdv}\n\nBonne journée,\n{prenom_exp}",
             "template_court": "Bonjour, dernier message promis. Si le timing est mauvais, dites-le moi simplement. Sinon : {lien_rdv}"},
        ],
    },
}

STATUTS = ["a_contacter", "repondu", "rdv", "gagne", "perdu", "opt_out", "epuise"]

STATUT_LABELS = {
    "a_contacter": "À contacter", "repondu": "Répondu", "rdv": "RDV pris",
    "gagne": "Gagné", "perdu": "Perdu", "opt_out": "Opt-out", "epuise": "Séquence épuisée",
}


def advance_updates(p: dict, etapes: list[dict]) -> dict:
    """Champs à $set après un envoi : étape suivante + date de relance, ou séquence épuisée."""
    current = int(p.get("etape_relance", 1))
    updates: dict = {"message_personnalise": "", "derniere_action": f"envoye_etape_{current}"}
    if current >= len(etapes):
        updates["statut"] = "epuise"
    else:
        next_step = etapes[current]  # index = current (0-based) → étape suivante
        delai = int(next_step.get("delai_jours", 3))
        updates["etape_relance"] = current + 1
        updates["date_prochaine_action"] = (datetime.now(timezone.utc) + timedelta(days=delai)).isoformat()
    return updates


def determine_profil(p: dict) -> str:
    site = p.get("site_web", "")
    note = int(p.get("note_site", 0) or 0)
    score = int(p.get("score_conversion", 0) or 0)
    if not has_real_website(site):
        return "pas_de_site"
    if score >= 80:
        return "signal_chaud"
    if note < 50:
        return "site_ancien"
    return "site_moyen"


_VAR_RE = re.compile(r"\{(\w+)\}")


def render_message(template: str, prospect: dict, settings: dict) -> str:
    """Remplit les variables du template. Les variables manquantes sont retirées proprement."""
    signal = as_str(prospect.get("signal_principal")) or as_str(prospect.get("qualite_site")) or "votre présence en ligne mérite mieux"
    site = prospect.get("site_web", "")

    # Argument de vente personnalisé basé sur l'analyse du site
    pitch = as_str(prospect.get("pitch_vendabilite"))
    raisons = prospect.get("raisons_vendabilite") or []
    if isinstance(raisons, list) and raisons:
        argument_vente = raisons[0].lower()
    elif pitch:
        argument_vente = pitch
    else:
        argument_vente = signal.lower() if signal else "votre site mérite mieux"

    variables = {
        "entreprise": as_str(prospect.get("entreprise")),
        "nom": as_str(prospect.get("nom")) or as_str(prospect.get("entreprise")),
        "ville": as_str(prospect.get("ville")),
        "metier": as_str(prospect.get("metier")) or "artisan",
        "site_web": site if has_real_website(site) else "",
        "signal": signal.lower() if signal else "",
        "argument_vente": argument_vente,
        "pitch": pitch,
        "note_site": str(prospect.get("note_site", 0) or 0),
        "prenom_exp": as_str(settings.get("prenom_expediteur")) or "Simon",
        "lien_rdv": as_str(settings.get("lien_rdv")),
        "offre": as_str(settings.get("offre")) or DEFAULT_OFFRE,
        "accroche_saison": accroche_saison(as_str(prospect.get("metier"))),
    }

    def repl(m):
        return variables.get(m.group(1), "")

    rendered = _VAR_RE.sub(repl, as_str(template))
    return re.sub(r"  +", " ", rendered).strip()
