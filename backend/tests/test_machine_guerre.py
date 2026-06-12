"""Tests de régression — machine de guerre : multi-canal, A/B objets, vendabilité."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from prospection import (  # noqa: E402
    DEFAULT_SCENARIOS, SCENARIO_VERSION, advance_updates, available_canaux,
    canal_plan, pick_objet, render_message,
)


def test_canal_plan_email_seul():
    p = {"email": "x@y.fr", "telephone": "", "linkedin_url": ""}
    assert canal_plan(p, 4) == ["email"] * 4


def test_canal_plan_trois_canaux_reste_sur_email():
    """Canal unique : même avec mobile + LinkedIn, toute la séquence reste sur email."""
    p = {"email": "x@y.fr", "telephone": "+33 6 12 34 56 78", "linkedin_url": "https://linkedin.com/in/x"}
    assert canal_plan(p, 4) == ["email"] * 4
    assert available_canaux(p) == ["email", "whatsapp", "linkedin"]


def test_canal_plan_email_mobile():
    p = {"email": "x@y.fr", "telephone": "06 12 34 56 78", "linkedin_url": ""}
    assert canal_plan(p, 4) == ["email"] * 4


def test_canal_plan_sans_email():
    p = {"email": "", "telephone": "06 98 76 54 32", "linkedin_url": "https://linkedin.com/in/x"}
    assert canal_plan(p, 4) == ["whatsapp"] * 4


def test_canal_plan_fixe_seul():
    p = {"email": "", "telephone": "01 23 45 67 89", "linkedin_url": ""}
    assert canal_plan(p, 4) == ["telephone"] * 4
    assert available_canaux(p) == ["telephone"]


def test_canal_plan_aucun_contact():
    assert canal_plan({"email": "", "telephone": "", "linkedin_url": ""}, 4) == []


def test_advance_updates_canal_stable():
    """Canal unique : après un envoi, le canal de l'étape suivante ne change pas."""
    etapes = DEFAULT_SCENARIOS["site_moyen"]["etapes"]
    p = {"etape_relance": 2, "plan_canaux": ["email", "email", "email", "email"],
         "canal_contact": "email"}
    u = advance_updates(p, etapes)
    assert u["etape_relance"] == 3
    assert u["canal_contact"] == "email"


def test_advance_updates_derniere_etape_epuise():
    etapes = DEFAULT_SCENARIOS["site_moyen"]["etapes"]
    p = {"etape_relance": 4, "plan_canaux": ["email"] * 4}
    u = advance_updates(p, etapes)
    assert u["statut"] == "epuise"
    assert "canal_contact" not in u


def test_pick_objet_variantes():
    step = {"objet": "Objet A", "objet_b": "Objet B"}
    assert pick_objet(step, "A") == "Objet A"
    assert pick_objet(step, "B") == "Objet B"
    assert pick_objet({"objet": "Objet A", "objet_b": ""}, "B") == "Objet A"


def test_tous_les_scenarios_ont_objet_b():
    assert SCENARIO_VERSION >= 3
    for sc in DEFAULT_SCENARIOS.values():
        for e in sc["etapes"]:
            assert e.get("objet"), f"{sc['profil']} étape {e['etape']} sans objet"
            assert e.get("objet_b"), f"{sc['profil']} étape {e['etape']} sans objet_b"
            assert e["objet"] != e["objet_b"]


def test_plus_de_simon_ici():
    """L'utilisateur ne veut plus de « Simon ici » / « bonjour c'est simon »."""
    interdits = ("c'est {prenom_exp}", "{prenom_exp} ici", "{prenom_exp} à nouveau",
                 "c'est encore {prenom_exp}")
    for sc in DEFAULT_SCENARIOS.values():
        for e in sc["etapes"]:
            for champ in ("template", "template_court"):
                txt = e.get(champ, "")
                for interdit in interdits:
                    assert interdit not in txt, f"« {interdit} » dans {sc['profil']} étape {e['etape']} ({champ})"


def test_argument_vente_injecte():
    p = {"entreprise": "Toiture Pro", "metier": "couvreur", "ville": "Lyon",
         "site_web": "https://toiture-pro.fr", "note_site": 35,
         "raisons_vendabilite": ["Site obsolète (35/100)"],
         "pitch_vendabilite": "Actuellement, concurrent avec un site moderne le dépasse sur Google."}
    tpl = DEFAULT_SCENARIOS["site_ancien"]["etapes"][0]["template"]
    msg = render_message(tpl, p, {"prenom_expediteur": "Simon"})
    assert "site obsolète (35/100)" in msg.lower()


def test_argument_vente_fallback_signal():
    p = {"entreprise": "X", "signal_principal": "Avis Google récents", "site_web": ""}
    msg = render_message("Test : {argument_vente}", p, {})
    assert "avis google récents" in msg.lower()
