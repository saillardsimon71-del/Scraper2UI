"""Iteration 4 — Tests des améliorations commerciales :
- Scénarios v2 (4 étapes, template_court, angle Google local)
- PUT scénario avec template_court
- Champ offre dans settings
- Rendu queue/sequence : template_court sur whatsapp/linkedin, long sur email
- Variables {offre} et {accroche_saison} bien remplacées (pas de bruts)
- Scoring : site_ancien > pas_de_site
"""
import os
import sys
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://856f08f4-547c-4196-840c-4ba45d1a8a0d.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

sys.path.insert(0, "/app/backend")


# ---------- 1. Scénarios v2 ----------
def test_all_scenarios_version_2_with_short_variants():
    r = requests.get(f"{API}/scenarios", timeout=10)
    assert r.status_code == 200
    scenarios = r.json()["scenarios"]
    profils = {s["profil"]: s for s in scenarios}
    assert set(profils.keys()) == {"pas_de_site", "site_ancien", "signal_chaud", "site_moyen"}
    for profil, sc in profils.items():
        assert sc["version"] == 2, f"{profil} version != 2 : {sc.get('version')}"
        etapes = sc["etapes"]
        assert len(etapes) == 4, f"{profil} a {len(etapes)} étapes au lieu de 4"
        for e in etapes:
            assert "template" in e and "objet" in e and "template_court" in e, \
                f"{profil} étape {e.get('etape')} manque un champ"
        # étape 1 = template_court vide
        assert etapes[0]["template_court"] == "", f"{profil} étape 1 template_court doit être vide"
        # étapes 2-4 = template_court non vide
        for i in (1, 2, 3):
            assert etapes[i]["template_court"], f"{profil} étape {i+1} template_court vide"


def test_pas_de_site_step2_has_google_local_angle():
    sc = next(s for s in requests.get(f"{API}/scenarios").json()["scenarios"]
              if s["profil"] == "pas_de_site")
    e2 = sc["etapes"][1]
    assert "{metier} {ville}" in e2["template"], "Étape 2 pas_de_site doit contenir {metier} {ville}"
    assert "fiche Google" in e2["template"].lower() or "Google" in e2["template"], \
        "Étape 2 pas_de_site doit mentionner la fiche Google"


# ---------- 2. PUT scénario avec template_court ----------
def test_put_scenario_with_template_court_preserves_version():
    # Lire l'état initial
    sc = next(s for s in requests.get(f"{API}/scenarios").json()["scenarios"]
              if s["profil"] == "site_moyen")
    original = [dict(e) for e in sc["etapes"]]
    # Modifier étape 2 (template_court)
    modified = [dict(e) for e in original]
    modified[1]["template_court"] = "TEST_ITER4_court — variant test"
    r = requests.put(f"{API}/scenarios/site_moyen", json={"etapes": modified}, timeout=10)
    assert r.status_code == 200, r.text
    # Vérifier persistance + version=2
    sc2 = next(s for s in requests.get(f"{API}/scenarios").json()["scenarios"]
               if s["profil"] == "site_moyen")
    assert sc2["version"] == 2
    assert sc2["etapes"][1]["template_court"].startswith("TEST_ITER4_court")
    # Restaurer
    requests.put(f"{API}/scenarios/site_moyen", json={"etapes": original}, timeout=10)


# ---------- 3. Settings offre ----------
def test_settings_offre_persists():
    initial = requests.get(f"{API}/settings", timeout=10).json()
    test_offre = "TEST_ITER4 un site à partir de 300 €, livré en 72 h"
    r = requests.put(f"{API}/settings", json={"offre": test_offre}, timeout=10)
    assert r.status_code == 200, r.text
    s = requests.get(f"{API}/settings", timeout=10).json()
    assert s.get("offre") == test_offre
    # Sensible : vérifier que sendgrid/imap pas écrasés
    assert s.get("sendgrid_api_key", "").startswith("SG."), "sendgrid_api_key écrasé !"
    assert s.get("email_expediteur") == "simon@sitequivend.fr"
    # Restaurer l'offre initiale
    requests.put(f"{API}/settings", json={"offre": initial.get("offre", "")}, timeout=10)


# ---------- 4. Rendu messages : variables, canal courts/longs ----------
@pytest.fixture
def prospect_whatsapp():
    """Crée prospect avec mobile (06) sans email → canal = whatsapp."""
    csv = b"entreprise,metier,ville,email,telephone\nTEST_ITER4_WhatsApp,plombier,Lyon,,0612345678\n"
    files = {"file": ("w.csv", csv, "text/csv")}
    requests.post(f"{API}/import", files=files, timeout=20).raise_for_status()
    lst = requests.get(f"{API}/prospects", params={"q": "TEST_ITER4_WhatsApp"}).json()
    pid = lst["items"][0]["id"]
    yield pid
    requests.delete(f"{API}/prospects/{pid}", timeout=10)


@pytest.fixture
def prospect_email():
    """Crée prospect avec email → canal = email."""
    csv = b"entreprise,metier,ville,email,telephone\nTEST_ITER4_Email,plombier,Lyon,test_iter4@example.com,0612345678\n"
    files = {"file": ("e.csv", csv, "text/csv")}
    requests.post(f"{API}/import", files=files, timeout=20).raise_for_status()
    lst = requests.get(f"{API}/prospects", params={"q": "TEST_ITER4_Email"}).json()
    pid = lst["items"][0]["id"]
    yield pid
    requests.delete(f"{API}/prospects/{pid}", timeout=10)


def test_whatsapp_sequence_uses_short_variants(prospect_whatsapp):
    d = requests.get(f"{API}/prospects/{prospect_whatsapp}").json()
    assert d["canal"] == "whatsapp", f"canal={d.get('canal')}"
    seq = d["sequence"]
    assert len(seq) == 4
    # Étapes 2-4 doivent contenir le rendu du template_court — vérification : pas de "{offre}" bruts et message court
    for idx in (1, 2, 3):
        msg = seq[idx]["message"]
        assert msg, f"étape {idx+1} message vide"
        assert "{offre}" not in msg and "{accroche_saison}" not in msg, \
            f"variable brute restante à l'étape {idx+1} : {msg}"
        assert "{lien_rdv}" not in msg
    # Sanity : le message étape 2 whatsapp doit être plus court que le template long de pas_de_site
    # (heuristique : < 400 chars)
    assert len(seq[1]["message"]) < 400, f"étape 2 whatsapp trop long : {len(seq[1]['message'])}"


def test_email_sequence_uses_long_templates(prospect_email):
    d = requests.get(f"{API}/prospects/{prospect_email}").json()
    assert d["canal"] == "email", f"canal={d.get('canal')}"
    seq = d["sequence"]
    # Email : templates longs → étape 4 (récap final) > 200 chars typiquement
    msg4 = seq[3]["message"]
    assert "{offre}" not in msg4 and "{accroche_saison}" not in msg4
    assert len(msg4) > 200, f"étape 4 email trop courte : {len(msg4)} chars : {msg4}"


def test_queue_contains_accroche_saison_field():
    r = requests.get(f"{API}/queue", timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    if items:
        item = items[0]
        assert "accroche_saison" in item, f"champ accroche_saison absent : {list(item.keys())}"


# ---------- 5. Scoring : site_ancien > pas_de_site ----------
def test_scoring_site_ancien_beats_pas_de_site():
    from scraper_core import compute_score
    base = {"joignable": True, "email": "x@y.fr", "score_signaux": 0, "whatsapp": False, "rating_google": 0}
    sans_site = {**base, "site_web": "", "note_site": 0}
    avec_vieux_site = {**base, "site_web": "http://example.com", "note_site": 40}
    s1, _ = compute_score(sans_site)
    s2, _ = compute_score(avec_vieux_site)
    assert s2 > s1, f"site_ancien ({s2}) doit > pas_de_site ({s1})"


# ---------- 6. accroche_saison logique ----------
def test_accroche_saison_couvreur_june_returns_text():
    from prospection import accroche_saison
    # Juin = mois 6 → fenêtre couvreur (5-9)
    out = accroche_saison("couvreur", month=6)
    assert out and "toiture" in out.lower() or "automne" in out.lower()


def test_accroche_saison_peintre_june_empty():
    from prospection import accroche_saison
    # Juin = mois 6 → peintre hors fenêtre (12-3)
    out = accroche_saison("peintre", month=6)
    assert out == ""
