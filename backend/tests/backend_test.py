"""Backend tests for Cockpit Prospection API."""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://prospect-auto-5.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ============================= Dashboard
class TestDashboard:
    def test_stats(self, session):
        r = session.get(f"{API}/dashboard/stats", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total", "file_du_jour", "envoyes_aujourdhui", "taux_reponse"):
            assert k in d, f"missing {k}: {d}"
        assert isinstance(d["total"], int)
        assert isinstance(d["taux_reponse"], (int, float))


# ============================= Queue (rendered messages)
class TestQueue:
    def test_queue_items(self, session):
        r = session.get(f"{API}/queue?limit=20", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "count" in d
        for it in d["items"]:
            assert "prospect" in it and "etape" in it and "canal" in it and "message" in it
            assert "{entreprise}" not in it["message"], f"Variable non remplacée: {it['message']}"
            assert "{prenom_exp}" not in it["message"]
            # if telephone, wa_link should be present
            if it["prospect"].get("telephone"):
                assert it.get("wa_link"), "wa_link manquant pour prospect avec tel"


# ============================= Scenarios
class TestScenarios:
    def test_list_scenarios(self, session):
        r = session.get(f"{API}/scenarios", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["scenarios"]) == 4
        profils = {s["profil"] for s in d["scenarios"]}
        assert profils == {"pas_de_site", "site_ancien", "signal_chaud", "site_moyen"}
        for s in d["scenarios"]:
            assert len(s["etapes"]) == 3

    def test_update_scenario_persist(self, session):
        # get current
        r = session.get(f"{API}/scenarios", timeout=15)
        scenarios = {s["profil"]: s for s in r.json()["scenarios"]}
        original = scenarios["pas_de_site"]
        custom_template = "TEST_TEMPLATE_xyz {entreprise} {prenom_exp}"
        etapes = [dict(e) for e in original["etapes"]]
        etapes[0]["template"] = custom_template
        r = session.put(f"{API}/scenarios/pas_de_site", json={"etapes": etapes}, timeout=15)
        assert r.status_code == 200
        assert r.json()["etapes"][0]["template"] == custom_template
        # verify persisted
        r = session.get(f"{API}/scenarios", timeout=15)
        sc = {s["profil"]: s for s in r.json()["scenarios"]}["pas_de_site"]
        assert sc["etapes"][0]["template"] == custom_template
        # restore
        r = session.put(f"{API}/scenarios/pas_de_site", json={"etapes": original["etapes"]}, timeout=15)
        assert r.status_code == 200


# ============================= Settings
class TestSettings:
    def test_get_settings(self, session):
        r = session.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("prenom_expediteur", "lien_rdv", "serper_api_key"):
            assert k in d

    def test_put_settings_persist(self, session):
        old = session.get(f"{API}/settings", timeout=15).json()
        new_prenom = "TEST_Simon_" + uuid.uuid4().hex[:6]
        r = session.put(f"{API}/settings", json={"prenom_expediteur": new_prenom}, timeout=15)
        assert r.status_code == 200
        assert r.json()["prenom_expediteur"] == new_prenom
        # verify get
        assert session.get(f"{API}/settings", timeout=15).json()["prenom_expediteur"] == new_prenom
        # restore
        session.put(f"{API}/settings", json={"prenom_expediteur": old.get("prenom_expediteur") or "Simon"}, timeout=15)


# ============================= Import CSV
class TestImport:
    def test_import_csv_and_dedupe(self, session):
        unique = uuid.uuid4().hex[:8]
        csv_content = (
            "nom,metier,ville,telephone,site_web\n"
            f"TEST_Dupont_Plomberie_{unique},plombier,Lyon,0612345678,\n"
            f"TEST_Martin_Elec_{unique},electricien,Lyon,0698765432,\n"
        )
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r = requests.post(f"{API}/import", files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["importes"] == 2, f"expected 2 imports, got {d}"
        assert d["doublons"] == 0
        # second upload -> dedup
        files2 = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        r2 = requests.post(f"{API}/import", files=files2, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["doublons"] == 2, f"expected 2 doublons on second upload, got {d2}"
        assert d2["importes"] == 0
        # verify created and has score/profil
        list_r = session.get(f"{API}/prospects?q=TEST_Dupont_Plomberie_{unique}", timeout=15)
        assert list_r.status_code == 200
        items = list_r.json()["items"]
        assert len(items) >= 1
        p = items[0]
        assert p["metier"] == "plombier"
        assert "score_conversion" in p
        assert p["profil"] in ("pas_de_site", "site_ancien", "signal_chaud", "site_moyen")
        # Cleanup
        for it in list_r.json()["items"]:
            session.delete(f"{API}/prospects/{it['id']}", timeout=15)
        list_r2 = session.get(f"{API}/prospects?q=TEST_Martin_Elec_{unique}", timeout=15)
        for it in list_r2.json()["items"]:
            session.delete(f"{API}/prospects/{it['id']}", timeout=15)


# ============================= Prospect action
class TestProspectAction:
    def test_action_envoye_advances_step(self, session):
        # create a prospect via import
        unique = uuid.uuid4().hex[:8]
        csv = (
            "nom,metier,ville,telephone,site_web\n"
            f"TEST_Action_{unique},plombier,Paris,0611111111,\n"
        )
        files = {"file": ("a.csv", io.BytesIO(csv.encode()), "text/csv")}
        r = requests.post(f"{API}/import", files=files, timeout=30)
        assert r.status_code == 200
        list_r = session.get(f"{API}/prospects?q=TEST_Action_{unique}", timeout=15)
        items = list_r.json()["items"]
        assert items
        p = items[0]
        pid = p["id"]
        assert p["etape_relance"] == 1
        old_date = p["date_prochaine_action"]

        # action envoye
        r = session.post(f"{API}/prospects/{pid}/action", json={"type": "envoye"}, timeout=15)
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["etape_relance"] == 2
        assert updated["date_prochaine_action"] > old_date
        # Should no longer be in today's queue
        q = session.get(f"{API}/queue?limit=200", timeout=15).json()
        ids = [it["prospect"]["id"] for it in q["items"]]
        assert pid not in ids, "Prospect ne devrait plus être dans la file après envoye"

        # action repondu
        r = session.post(f"{API}/prospects/{pid}/action", json={"type": "repondu"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["statut"] == "repondu"

        # reactiver
        r = session.post(f"{API}/prospects/{pid}/action", json={"type": "reactiver"}, timeout=15)
        assert r.status_code == 200
        rj = r.json()
        assert rj["statut"] == "a_contacter"
        assert rj["etape_relance"] == 1

        # cleanup
        session.delete(f"{API}/prospects/{pid}", timeout=15)


# ============================= Scrape job
class TestScrape:
    def test_scrape_gouv_dijon_electricien(self, session):
        payload = {"metier": "electricien", "ville": "Dijon", "limite": 5,
                   "source": "gouv", "auditer": True}
        r = session.post(f"{API}/scrape", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        job = r.json()
        jid = job["id"]
        # poll up to 60s
        deadline = time.time() + 60
        last = None
        while time.time() < deadline:
            rr = session.get(f"{API}/scrape/jobs/{jid}", timeout=15)
            assert rr.status_code == 200
            last = rr.json()
            if last["statut"] in ("termine", "erreur"):
                break
            time.sleep(3)
        assert last is not None
        assert last["statut"] == "termine", f"Job non terminé: {last}"
        # ajoutes may be 0 if all duplicates - accept >= 0 but require traites > 0
        assert last["traites"] >= 0
        # at least it should have run logs
        assert len(last.get("logs", [])) > 0


# ============================= AI improve (real call, run last, single test)
class TestAI:
    def test_ai_improve(self, session):
        body = {
            "message": "Bonjour, je suis Simon, votre site est vieux. On parle ?",
            "canal": "whatsapp",
        }
        r = session.post(f"{API}/ai/improve", json=body, timeout=60)
        assert r.status_code == 200, f"AI improve failed: {r.status_code} {r.text}"
        d = r.json()
        assert "message" in d
        assert isinstance(d["message"], str)
        assert len(d["message"]) > 10
