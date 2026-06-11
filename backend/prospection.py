"""Scénarios de relance, détermination du profil et rendu des messages."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from scraper_core import as_str, has_real_website

PROFILS = ["pas_de_site", "site_ancien", "signal_chaud", "site_moyen"]

PROFIL_LABELS = {
    "pas_de_site": "Pas de site",
    "site_ancien": "Site ancien",
    "signal_chaud": "Signal chaud",
    "site_moyen": "Site moyen",
}

# delai_jours = jours d'attente APRÈS l'étape précédente (étape 1 : immédiat)
DEFAULT_SCENARIOS = {
    "pas_de_site": {
        "profil": "pas_de_site",
        "label": "Pas de site",
        "description": "Prospect sans aucun site web — le besoin est maximal.",
        "etapes": [
            {"etape": 1, "delai_jours": 0, "canal": "whatsapp",
             "template": "Bonjour, je suis {prenom_exp}, je travaille dans le web. Je cherchais le site de {entreprise} pour voir vos réalisations, mais je n'ai rien trouvé en ligne. Vous avez une page quelque part ?"},
            {"etape": 2, "delai_jours": 3, "canal": "linkedin",
             "template": "Bonjour, {prenom_exp}, spécialiste web. Je n'ai pas trouvé de site pour {entreprise} — aujourd'hui 8 clients sur 10 cherchent leur {metier} sur Google avant d'appeler. Je peux vous montrer en 2 min ce que ça donnerait pour vous ?"},
            {"etape": 3, "delai_jours": 4, "canal": "whatsapp",
             "template": "Bonjour, c'est encore {prenom_exp}. Dernière relance promis : j'ai préparé une idée de site pour {entreprise}, simple et efficace pour récupérer des demandes de devis. Je vous l'envoie ? {lien_rdv}"},
            {"etape": 4, "delai_jours": 3, "canal": "email",
             "objet": "Un site pour {entreprise} ? Quelques idées concrètes",
             "template": "Bonjour,\n\nJe me permets un dernier message, par écrit cette fois : je suis {prenom_exp}, spécialiste web, et je n'ai trouvé aucun site pour {entreprise}.\n\nAujourd'hui, 8 clients sur 10 cherchent leur {metier} sur Google avant d'appeler. Un site simple — vos réalisations, vos avis clients, un formulaire de devis — peut faire une vraie différence sur vos demandes entrantes.\n\nSi vous voulez voir ce que ça donnerait pour vous, on peut en parler 15 minutes : {lien_rdv}\n\nBonne journée,\n{prenom_exp}"},
        ],
    },
    "site_ancien": {
        "profil": "site_ancien",
        "label": "Site ancien",
        "description": "Site existant mais obsolète (note < 50/100).",
        "etapes": [
            {"etape": 1, "delai_jours": 0, "canal": "whatsapp",
             "template": "Bonjour, je suis {prenom_exp}. Je suis passé sur {site_web} — beau métier ! Par contre le site mériterait un coup de jeune ({signal}). Ça vous dirait qu'on en parle 2 minutes ?"},
            {"etape": 2, "delai_jours": 3, "canal": "linkedin",
             "template": "Bonjour, {prenom_exp}, spécialiste web. J'ai analysé le site de {entreprise} : note {note_site}/100. Quelques améliorations simples pourraient vous amener nettement plus de demandes de devis. Je vous envoie le détail ?"},
            {"etape": 3, "delai_jours": 4, "canal": "whatsapp",
             "template": "Bonjour, {prenom_exp} à nouveau. Dernier message : j'ai noté 2-3 améliorations concrètes pour {site_web} qui pourraient augmenter vos appels entrants. Ça vous intéresse ? {lien_rdv}"},
            {"etape": 4, "delai_jours": 3, "canal": "email",
             "objet": "Quelques pistes concrètes pour le site de {entreprise}",
             "template": "Bonjour,\n\nJe suis {prenom_exp}, spécialiste web. J'ai analysé {site_web} et je vous écris par email pour vous laisser une trace écrite : {signal}.\n\nQuelques améliorations simples pourraient vous amener nettement plus de demandes de devis — être mieux trouvé sur Google, faciliter l'appel depuis un téléphone, rassurer avec vos réalisations.\n\nSi ça vous intéresse, je vous montre tout en 15 minutes : {lien_rdv}\n\nBonne journée,\n{prenom_exp}"},
        ],
    },
    "signal_chaud": {
        "profil": "signal_chaud",
        "label": "Signal chaud",
        "description": "Fort signal d'achat détecté (score ≥ 80) — séquence rapide.",
        "etapes": [
            {"etape": 1, "delai_jours": 0, "canal": "whatsapp",
             "template": "Bonjour, je suis {prenom_exp}, spécialiste web. En regardant {entreprise} j'ai remarqué : {signal}. C'est exactement le genre de situation où une présence web optimisée fait la différence sur les devis. On échange 2 minutes ?"},
            {"etape": 2, "delai_jours": 2, "canal": "linkedin",
             "template": "Bonjour, {prenom_exp} ici. Je vous ai écrit sur WhatsApp au sujet de {entreprise} ({signal}). J'ai déjà quelques pistes concrètes — dispo pour un appel rapide cette semaine ? {lien_rdv}"},
            {"etape": 3, "delai_jours": 3, "canal": "whatsapp",
             "template": "Bonjour, dernier message de ma part. L'opportunité est réelle pour {entreprise} : {signal}. Si le timing est mauvais, dites-le moi simplement et je ne vous relancerai plus. Bonne journée !"},
            {"etape": 4, "delai_jours": 2, "canal": "email",
             "objet": "{entreprise} : les pistes dont je vous parlais",
             "template": "Bonjour,\n\n{prenom_exp} ici, spécialiste web. Je vous ai contacté récemment au sujet de {entreprise} : {signal}.\n\nC'est exactement le genre de moment où une présence web optimisée fait la différence sur les devis. J'ai déjà quelques pistes concrètes à vous montrer.\n\nUn créneau de 15 minutes cette semaine ? {lien_rdv}\n\nBonne journée,\n{prenom_exp}"},
        ],
    },
    "site_moyen": {
        "profil": "site_moyen",
        "label": "Site moyen",
        "description": "Site correct mais perfectible (note 50-79/100).",
        "etapes": [
            {"etape": 1, "delai_jours": 0, "canal": "whatsapp",
             "template": "Bonjour, je suis {prenom_exp}, spécialiste web. J'ai vu votre site {site_web}, il a du potentiel mais quelques points pourraient être améliorés pour attirer plus de clients ({signal}). Vous êtes ouvert à un échange rapide ?"},
            {"etape": 2, "delai_jours": 4, "canal": "linkedin",
             "template": "Bonjour, {prenom_exp}. J'ai audité le site de {entreprise} (note {note_site}/100) : il y a des gains rapides possibles côté visibilité Google et conversion. Je partage l'audit complet si ça vous intéresse."},
            {"etape": 3, "delai_jours": 4, "canal": "whatsapp",
             "template": "Bonjour, {prenom_exp} à nouveau. Je clos mon suivi sur {entreprise} — si améliorer {site_web} devient une priorité, je reste disponible. {lien_rdv}"},
            {"etape": 4, "delai_jours": 3, "canal": "email",
             "objet": "Audit de {site_web} : les gains rapides pour {entreprise}",
             "template": "Bonjour,\n\nJe suis {prenom_exp}, spécialiste web. J'ai audité le site de {entreprise} ({site_web}) : il a du potentiel, et quelques gains rapides sont possibles côté visibilité Google et demandes de devis.\n\nJe vous partage volontiers le détail de l'audit — c'est gratuit et sans engagement.\n\nOn en parle 15 minutes ? {lien_rdv}\n\nBonne journée,\n{prenom_exp}"},
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
    variables = {
        "entreprise": as_str(prospect.get("entreprise")),
        "nom": as_str(prospect.get("nom")) or as_str(prospect.get("entreprise")),
        "ville": as_str(prospect.get("ville")),
        "metier": as_str(prospect.get("metier")) or "artisan",
        "site_web": site if has_real_website(site) else "",
        "signal": signal.lower() if signal else "",
        "note_site": str(prospect.get("note_site", 0) or 0),
        "prenom_exp": as_str(settings.get("prenom_expediteur")) or "Simon",
        "lien_rdv": as_str(settings.get("lien_rdv")),
    }

    def repl(m):
        return variables.get(m.group(1), "")

    rendered = _VAR_RE.sub(repl, as_str(template))
    return re.sub(r"  +", " ", rendered).strip()
