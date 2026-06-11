"""Iteration 3 — Tests Cockpit de Prospection (autopilot, settings, prospects, scraper, IA).

⚠️ Real SendGrid key in DB. Tests qui envoient des emails utilisent EXCLUSIVEMENT
simon@sitequivend.fr (l'adresse du propriétaire) et nettoient leurs prospects.
"""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://7d25508e-43ab-4cfc-860d-5412eeeaf5f2.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


# -------- Dashboard & queue ---------
def test_dashboard_stats():
    r = requests.get(f"{API}/dashboard/stats", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("total", "file_du_jour", "envoyes_aujourdhui", "repondus", "contactes",
              "taux_reponse", "par_statut", "par_niveau"):
        assert k in d, f"clé manquante {k}"
    assert isinstance(d["total"], int)


def test_queue_endpoint():
    r = requests.get(f"{API}/queue", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and "count" in d


# -------- Settings (préchargés en DB) ---------
def test_settings_preloaded():
    r = requests.get(f"{API}/settings", timeout=10)
    assert r.status_code == 200
    s = r.json()
    assert s["prenom_expediteur"] == "Simon"
    assert "calendly.com/sitequivend" in s["lien_rdv"]
    assert s["sendgrid_api_key"].startswith("SG.")
    assert s["email_expediteur"] == "simon@sitequivend.fr"
    assert s["autopilot_actif"] is True


def test_settings_put_persists_autopilot():
    # Lire la valeur initiale
    initial = requests.get(f"{API}/settings", timeout=10).json()
    new_quota = 47 if initial["autopilot_quota_jour"] != 47 else 48
    r = requests.put(f"{API}/settings",
                     json={"autopilot_quota_jour": new_quota, "autopilot_actif": True},
                     timeout=10)
    assert r.status_code == 200
    assert r.json()["autopilot_quota_jour"] == new_quota
    # Vérifier la persistance via GET
    s = requests.get(f"{API}/settings", timeout=10).json()
    assert s["autopilot_quota_jour"] == new_quota
    assert s["autopilot_actif"] is True
    # Remettre la valeur précédente pour ne pas polluer
    requests.put(f"{API}/settings",
                 json={"autopilot_quota_jour": initial["autopilot_quota_jour"]},
                 timeout=10)


# -------- Scénarios (4 profils, étape 4 = email avec objet) --------
def test_scenarios_have_4_profiles_with_email_step4():
    r = requests.get(f"{API}/scenarios", timeout=10)
    assert r.status_code == 200
    scenarios = r.json()["scenarios"]
    assert len(scenarios) == 4
    profils = {s["profil"] for s in scenarios}
    assert profils == {"pas_de_site", "site_ancien", "signal_chaud", "site_moyen"}
    for s in scenarios:
        etapes = s["etapes"]
        assert len(etapes) == 4, f"{s['profil']} doit avoir 4 étapes"
        e4 = etapes[3]
        assert e4["canal"] == "email", f"{s['profil']} étape 4 doit être email"
        assert e4.get("objet"), f"{s['profil']} étape 4 doit avoir un objet"


def test_scenario_update_and_restore():
    # GET initial
    sc = next(s for s in requests.get(f"{API}/scenarios").json()["scenarios"]
              if s["profil"] == "site_moyen")
    original = sc["etapes"]
    # PUT — modifier étape 1
    modified = [dict(e) for e in original]
    modified[0]["template"] = "TEST_TEMPLATE — " + modified[0]["template"]
    r = requests.put(f"{API}/scenarios/site_moyen", json={"etapes": modified}, timeout=10)
    assert r.status_code == 200
    # Vérifier persistance
    sc2 = next(s for s in requests.get(f"{API}/scenarios").json()["scenarios"]
               if s["profil"] == "site_moyen")
    assert sc2["etapes"][0]["template"].startswith("TEST_TEMPLATE")
    # Restaurer
    requests.put(f"{API}/scenarios/site_moyen", json={"etapes": original}, timeout=10)


# -------- Prospects CRUD + action ---------
@pytest.fixture
def test_prospect():
    """Crée un prospect via import (helper). Yield id, puis cleanup."""
    # On utilise direct l'API : créons via /import avec un mini CSV
    csv = b"entreprise,metier,ville,email,telephone\nTEST_ITER3_AcmeBat,plombier,Lyon,simon@sitequivend.fr,0612345678\n"
    files = {"file": ("test.csv", csv, "text/csv")}
    r = requests.post(f"{API}/import", files=files, timeout=20)
    assert r.status_code == 200, r.text
    # Récupérer l'id du prospect créé
    lst = requests.get(f"{API}/prospects", params={"q": "TEST_ITER3_AcmeBat"}).json()
    assert lst["total"] >= 1
    pid = lst["items"][0]["id"]
    yield pid
    # Cleanup
    requests.delete(f"{API}/prospects/{pid}", timeout=10)


def test_prospects_list_and_filter(test_prospect):
    r = requests.get(f"{API}/prospects", params={"q": "TEST_ITER3"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_prospect_get_detail(test_prospect):
    r = requests.get(f"{API}/prospects/{test_prospect}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "prospect" in d and "sequence" in d
    assert len(d["sequence"]) == 4


def test_prospect_patch_email(test_prospect):
    new_email = "TEST_iter3_changed@example.com"
    r = requests.patch(f"{API}/prospects/{test_prospect}",
                       json={"email": new_email}, timeout=10)
    assert r.status_code == 200
    assert r.json()["email"] == new_email
    # Remettre l'email original (simon@) pour les tests autopilot
    requests.patch(f"{API}/prospects/{test_prospect}",
                   json={"email": "simon@sitequivend.fr"}, timeout=10)


def test_prospect_action_envoye_advances_step(test_prospect):
    """Régression refactor advance_updates : action envoye doit incrémenter étape."""
    before = requests.get(f"{API}/prospects/{test_prospect}").json()["prospect"]
    assert before["etape_relance"] == 1
    r = requests.post(f"{API}/prospects/{test_prospect}/action",
                      json={"type": "envoye"}, timeout=10)
    assert r.status_code == 200
    after = r.json()
    assert after["etape_relance"] == 2, f"étape non incrémentée : {after['etape_relance']}"
    # date_prochaine_action repoussée
    assert after["date_prochaine_action"] > before["date_prochaine_action"]


# -------- Autopilot endpoints --------
def test_autopilot_status_keys():
    r = requests.get(f"{API}/autopilot/status", timeout=10)
    assert r.status_code == 200
    d = r.json()
    for k in ("actif", "configure", "envoyes_aujourdhui", "quota",
              "en_attente", "fenetre_ok"):
        assert k in d
    assert d["configure"] is True  # sendgrid + sender configurés


def test_autopilot_log_endpoint():
    r = requests.get(f"{API}/autopilot/log", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d
    assert isinstance(d["items"], list)


# -------- Autopilot full flow — RÉEL : envoie un email à simon@sitequivend.fr --------
def test_autopilot_run_sends_to_test_prospect():
    """⚠️ Envoie un VRAI email à simon@sitequivend.fr via SendGrid."""
    # Créer un prospect spécifique étape 4 canal email, échéance passée
    csv = b"entreprise,metier,ville,email,telephone\nTEST_ITER3_Autopilot,plombier,Lyon,simon@sitequivend.fr,0612345678\n"
    files = {"file": ("autopilot.csv", csv, "text/csv")}
    r = requests.post(f"{API}/import", files=files, timeout=20)
    assert r.status_code == 200, r.text

    lst = requests.get(f"{API}/prospects", params={"q": "TEST_ITER3_Autopilot"}).json()
    assert lst["total"] >= 1
    pid = lst["items"][0]["id"]

    try:
        # Forcer profil=pas_de_site, etape=4, date passée
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        # PATCH ne supporte pas etape_relance/date_prochaine_action — passons par mongo direct
        # Au lieu de mongo, on utilise prospect_action 'envoye' 3 fois pour atteindre étape 4
        for _ in range(3):
            requests.post(f"{API}/prospects/{pid}/action",
                          json={"type": "envoye"}, timeout=10)
        cur = requests.get(f"{API}/prospects/{pid}").json()["prospect"]
        assert cur["etape_relance"] == 4

        # Force profil=pas_de_site pour assurer canal=email à l'étape 4
        requests.patch(f"{API}/prospects/{pid}", json={"profil": "pas_de_site"}, timeout=10)

        # Lien direct mongo pour date_prochaine_action et statut a_contacter (PATCH ok pour statut)
        requests.patch(f"{API}/prospects/{pid}", json={"statut": "a_contacter"}, timeout=10)
        # date_prochaine_action est remise à now() quand statut=a_contacter dans PATCH,
        # donc elle est <= now → éligible
        time.sleep(1)

        # Lancer run autopilot
        r = requests.post(f"{API}/autopilot/run", timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res.get("executed") is True, f"executed != true : {res}"
        # envoyes peut être 0 si quota atteint, mais on attend >=1 dans un env neuf
        assert res.get("envoyes", 0) >= 1, f"aucun email envoyé : {res}"

        # Vérifier statut prospect épuisé (étape 4 + envoye → epuise)
        after = requests.get(f"{API}/prospects/{pid}").json()["prospect"]
        assert after["statut"] == "epuise", f"statut attendu epuise, eu {after['statut']}"

        # Vérifier log
        log = requests.get(f"{API}/autopilot/log").json()["items"]
        assert any(e.get("prospect_id") == pid for e in log), "Aucune entrée log pour ce prospect"
    finally:
        requests.delete(f"{API}/prospects/{pid}", timeout=10)


# -------- IA (1 seul appel — coût LLM) --------
def test_ai_improve_one_call():
    r = requests.post(f"{API}/ai/improve",
                      json={"message": "Bonjour, je vends des sites web. Vous voulez ?",
                            "canal": "whatsapp"},
                      timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "message" in d
    assert len(d["message"]) > 10
    assert len(d["message"]) <= 600  # marge


# -------- Scraper (job rapide gouv, limite 3) --------
def test_scraper_job_completes():
    r = requests.post(f"{API}/scrape",
                      json={"metier": "plombier", "ville": "Lyon", "limite": 3,
                            "source": "gouv", "auditer": False},
                      timeout=15)
    assert r.status_code == 200
    job_id = r.json()["id"]
    # Poll jusqu'à 60s
    for _ in range(30):
        time.sleep(2)
        j = requests.get(f"{API}/scrape/jobs/{job_id}").json()
        if j["statut"] in ("termine", "erreur"):
            break
    assert j["statut"] == "termine", f"Job non terminé : {j.get('statut')} logs={j.get('logs')}"
    # ajoutes peut être 0 si tout en doublons, mais traites > 0
    assert j.get("progress") == 100
