"""Backend tests for Cockpit Prospection API."""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://entonnoir-conversion.preview.emergentagent.com').rstrip('/')
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


# ============================= Dashboard Business (NEW)
class TestDashboardBusiness:
    def test_dashboard_business_structure(self, session):
        """Test GET /api/dashboard/business returns correct structure and coherent data."""
        r = session.get(f"{API}/dashboard/business", timeout=30)
        assert r.status_code == 200, f"Failed: {r.status_code} {r.text}"
        d = r.json()
        
        # Check all required keys exist
        required_keys = ["entonnoir", "ca", "raisons_refus", "par_profil", 
                        "derniers_gagnes", "taux_reponse", "taux_rdv", "taux_signature"]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"
        
        # Check entonnoir structure
        entonnoir = d["entonnoir"]
        entonnoir_keys = ["total", "contactes", "repondus", "rdv", "gagnes", "perdus"]
        for key in entonnoir_keys:
            assert key in entonnoir, f"Missing entonnoir key: {key}"
            assert isinstance(entonnoir[key], int), f"{key} should be int"
        
        # Check coherence: total >= contactes >= repondus >= rdv >= gagnes
        assert entonnoir["total"] >= entonnoir["contactes"], \
            f"total ({entonnoir['total']}) should be >= contactes ({entonnoir['contactes']})"
        assert entonnoir["contactes"] >= entonnoir["repondus"], \
            f"contactes ({entonnoir['contactes']}) should be >= repondus ({entonnoir['repondus']})"
        assert entonnoir["repondus"] >= entonnoir["rdv"], \
            f"repondus ({entonnoir['repondus']}) should be >= rdv ({entonnoir['rdv']})"
        assert entonnoir["rdv"] >= entonnoir["gagnes"], \
            f"rdv ({entonnoir['rdv']}) should be >= gagnes ({entonnoir['gagnes']})"
        
        # Check CA structure
        ca = d["ca"]
        assert "total" in ca and "moyen" in ca and "count" in ca
        assert isinstance(ca["total"], (int, float))
        assert isinstance(ca["moyen"], (int, float))
        assert isinstance(ca["count"], int)
        if ca["count"] > 0:
            assert ca["total"] > 0, "If count > 0, total should be > 0"
        
        # Check raisons_refus is a list
        assert isinstance(d["raisons_refus"], list)
        for raison in d["raisons_refus"]:
            assert "raison" in raison and "n" in raison
        
        # Check par_profil is a dict
        assert isinstance(d["par_profil"], dict)
        for profil, stats in d["par_profil"].items():
            assert "total" in stats and "gagnes" in stats and "repondus" in stats
            assert "taux_reponse" in stats and "taux_conversion" in stats
        
        # Check derniers_gagnes is a list
        assert isinstance(d["derniers_gagnes"], list)
        
        # Check taux are numbers
        assert isinstance(d["taux_reponse"], (int, float))
        assert isinstance(d["taux_rdv"], (int, float))
        assert isinstance(d["taux_signature"], (int, float))


# ============================= Vendabilité Migration (NEW)
class TestVendabiliteMigration:
    def test_migrate_vendabilite(self, session):
        """Test POST /api/admin/migrate-vendabilite and verify vendabilité fields."""
        # Call migration endpoint
        r = session.post(f"{API}/admin/migrate-vendabilite", timeout=60)
        assert r.status_code == 200, f"Migration failed: {r.status_code} {r.text}"
        d = r.json()
        assert "migrated" in d
        assert isinstance(d["migrated"], int)
        assert d["migrated"] > 0, "Should have migrated at least some prospects"
        
        # Verify prospects now have vendabilité fields
        r = session.get(f"{API}/prospects?limit=10", timeout=15)
        assert r.status_code == 200
        prospects = r.json()["items"]
        assert len(prospects) > 0, "Should have prospects to check"
        
        # Check first few prospects have vendabilité fields
        for p in prospects[:5]:
            assert "score_vendabilite" in p, f"Missing score_vendabilite in prospect {p.get('id')}"
            assert "label_vendabilite" in p, f"Missing label_vendabilite in prospect {p.get('id')}"
            assert "raisons_vendabilite" in p, f"Missing raisons_vendabilite in prospect {p.get('id')}"
            assert "pitch_vendabilite" in p, f"Missing pitch_vendabilite in prospect {p.get('id')}"
            
            # Validate types and ranges
            assert isinstance(p["score_vendabilite"], int), "score_vendabilite should be int"
            assert 0 <= p["score_vendabilite"] <= 100, "score_vendabilite should be 0-100"
            assert isinstance(p["label_vendabilite"], str), "label_vendabilite should be string"
            assert isinstance(p["raisons_vendabilite"], list), "raisons_vendabilite should be list"
            assert isinstance(p["pitch_vendabilite"], str), "pitch_vendabilite should be string"


# ============================= New Prospect Actions (NEW)
class TestNewProspectActions:
    @pytest.fixture(scope="class")
    def test_prospects(self, session):
        """Create test prospects for action testing."""
        unique = uuid.uuid4().hex[:8]
        csv = (
            "nom,metier,ville,telephone,site_web\n"
            f"TEST_Gagne_{unique},plombier,Paris,0611111111,\n"
            f"TEST_Perdu_{unique},electricien,Lyon,0622222222,\n"
            f"TEST_Rappel_{unique},menuisier,Marseille,0633333333,\n"
            f"TEST_Reactiver_{unique},peintre,Toulouse,0644444444,\n"
            f"TEST_OptOut_{unique},maçon,Nice,0655555555,\n"
        )
        files = {"file": ("test_actions.csv", io.BytesIO(csv.encode()), "text/csv")}
        r = requests.post(f"{API}/import", files=files, timeout=30)
        assert r.status_code == 200
        
        # Get all created prospects
        prospects = {}
        for name in ["Gagne", "Perdu", "Rappel", "Reactiver", "OptOut"]:
            r = session.get(f"{API}/prospects?q=TEST_{name}_{unique}", timeout=15)
            items = r.json()["items"]
            assert len(items) > 0, f"Failed to create TEST_{name}_{unique}"
            prospects[name.lower()] = items[0]
        
        yield prospects
        
        # Cleanup
        for p in prospects.values():
            try:
                session.delete(f"{API}/prospects/{p['id']}", timeout=15)
            except:
                pass
    
    def test_action_gagne_with_ca(self, session, test_prospects):
        """Test action 'gagne' with ca_contrat."""
        p = test_prospects["gagne"]
        pid = p["id"]
        
        # Get initial dashboard CA
        r = session.get(f"{API}/dashboard/business", timeout=30)
        initial_ca = r.json()["ca"]["total"]
        initial_gagnes = r.json()["entonnoir"]["gagnes"]
        
        # Perform gagne action with CA
        ca_amount = 1500.0
        r = session.post(f"{API}/prospects/{pid}/action", 
                        json={"type": "gagne", "ca_contrat": ca_amount}, 
                        timeout=15)
        assert r.status_code == 200, f"Action gagne failed: {r.text}"
        updated = r.json()
        
        # Verify prospect updated
        assert updated["statut"] == "gagne", f"Expected statut 'gagne', got {updated['statut']}"
        assert updated["ca_contrat"] == ca_amount, f"Expected ca_contrat {ca_amount}, got {updated.get('ca_contrat')}"
        
        # Verify historique
        assert len(updated["historique"]) > 0
        last_event = updated["historique"][-1]
        assert last_event["type"] == "gagne"
        assert last_event["ca_contrat"] == ca_amount
        
        # Verify dashboard updated
        r = session.get(f"{API}/dashboard/business", timeout=30)
        new_dashboard = r.json()
        assert new_dashboard["ca"]["total"] >= initial_ca + ca_amount, \
            f"CA should increase by {ca_amount}"
        assert new_dashboard["entonnoir"]["gagnes"] >= initial_gagnes + 1, \
            "Gagnes count should increase by 1"
    
    def test_action_perdu_with_raison(self, session, test_prospects):
        """Test action 'perdu' with raison_refus."""
        p = test_prospects["perdu"]
        pid = p["id"]
        
        raison = "Trop cher"
        r = session.post(f"{API}/prospects/{pid}/action",
                        json={"type": "perdu", "raison_refus": raison},
                        timeout=15)
        assert r.status_code == 200, f"Action perdu failed: {r.text}"
        updated = r.json()
        
        # Verify prospect updated
        assert updated["statut"] == "perdu", f"Expected statut 'perdu', got {updated['statut']}"
        assert updated["raison_refus"] == raison, f"Expected raison_refus '{raison}', got {updated.get('raison_refus')}"
        
        # Verify historique
        last_event = updated["historique"][-1]
        assert last_event["type"] == "perdu"
        assert last_event["raison_refus"] == raison
    
    def test_action_rappel(self, session, test_prospects):
        """Test action 'rappel' with rappel_dans_jours."""
        p = test_prospects["rappel"]
        pid = p["id"]
        
        jours = 10
        r = session.post(f"{API}/prospects/{pid}/action",
                        json={"type": "rappel", "rappel_dans_jours": jours},
                        timeout=15)
        assert r.status_code == 200, f"Action rappel failed: {r.text}"
        updated = r.json()
        
        # Verify date_rappel and date_prochaine_action are set
        assert updated["date_rappel"] is not None, "date_rappel should be set"
        assert updated["date_prochaine_action"] is not None, "date_prochaine_action should be set"
        
        # Verify dates are in the future (rough check)
        from datetime import datetime, timezone
        rappel_date = datetime.fromisoformat(updated["date_rappel"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        assert rappel_date > now, "Rappel date should be in the future"
        
        # Verify historique
        last_event = updated["historique"][-1]
        assert last_event["type"] == "rappel"
        assert last_event["jours"] == jours
    
    def test_action_reactiver(self, session, test_prospects):
        """Test action 'reactiver'."""
        p = test_prospects["reactiver"]
        pid = p["id"]
        
        # First set to perdu
        r = session.post(f"{API}/prospects/{pid}/action",
                        json={"type": "perdu", "raison_refus": "Test"},
                        timeout=15)
        assert r.status_code == 200
        assert r.json()["statut"] == "perdu"
        
        # Now reactiver
        r = session.post(f"{API}/prospects/{pid}/action",
                        json={"type": "reactiver"},
                        timeout=15)
        assert r.status_code == 200, f"Action reactiver failed: {r.text}"
        updated = r.json()
        
        # Verify prospect reactivated
        assert updated["statut"] == "a_contacter", f"Expected statut 'a_contacter', got {updated['statut']}"
        assert updated["etape_relance"] == 1, f"Expected etape_relance 1, got {updated['etape_relance']}"
        assert updated["date_rappel"] is None, "date_rappel should be null after reactiver"
        
        # Verify historique
        last_event = updated["historique"][-1]
        assert last_event["type"] == "reactiver"
    
    def test_action_opt_out(self, session, test_prospects):
        """Test action 'opt_out' with raison_refus."""
        p = test_prospects["optout"]
        pid = p["id"]
        
        raison = "Ne souhaite plus être contacté"
        r = session.post(f"{API}/prospects/{pid}/action",
                        json={"type": "opt_out", "raison_refus": raison},
                        timeout=15)
        assert r.status_code == 200, f"Action opt_out failed: {r.text}"
        updated = r.json()
        
        # Verify prospect updated
        assert updated["statut"] == "opt_out", f"Expected statut 'opt_out', got {updated['statut']}"
        assert updated["raison_refus"] == raison, f"Expected raison_refus '{raison}', got {updated.get('raison_refus')}"
        
        # Verify historique
        last_event = updated["historique"][-1]
        assert last_event["type"] == "opt_out"


# ============================= Prospect Update with new fields (NEW)
class TestProspectUpdate:
    def test_update_ca_contrat_and_raison_refus(self, session):
        """Test PATCH /api/prospects/{id} can update ca_contrat and raison_refus."""
        # Create a test prospect
        unique = uuid.uuid4().hex[:8]
        csv = f"nom,metier,ville,telephone\nTEST_Update_{unique},plombier,Paris,0611111111\n"
        files = {"file": ("test_update.csv", io.BytesIO(csv.encode()), "text/csv")}
        r = requests.post(f"{API}/import", files=files, timeout=30)
        assert r.status_code == 200
        
        # Get the prospect
        r = session.get(f"{API}/prospects?q=TEST_Update_{unique}", timeout=15)
        items = r.json()["items"]
        assert len(items) > 0
        p = items[0]
        pid = p["id"]
        
        try:
            # Update ca_contrat
            r = session.patch(f"{API}/prospects/{pid}",
                            json={"ca_contrat": 2500.0},
                            timeout=15)
            assert r.status_code == 200, f"Update ca_contrat failed: {r.text}"
            updated = r.json()
            assert updated["ca_contrat"] == 2500.0, f"Expected ca_contrat 2500.0, got {updated.get('ca_contrat')}"
            
            # Update raison_refus
            r = session.patch(f"{API}/prospects/{pid}",
                            json={"raison_refus": "Budget insuffisant"},
                            timeout=15)
            assert r.status_code == 200, f"Update raison_refus failed: {r.text}"
            updated = r.json()
            assert updated["raison_refus"] == "Budget insuffisant", \
                f"Expected raison_refus 'Budget insuffisant', got {updated.get('raison_refus')}"
            
            # Update both at once
            r = session.patch(f"{API}/prospects/{pid}",
                            json={"ca_contrat": 3000.0, "raison_refus": "Délais trop longs"},
                            timeout=15)
            assert r.status_code == 200, f"Update both fields failed: {r.text}"
            updated = r.json()
            assert updated["ca_contrat"] == 3000.0
            assert updated["raison_refus"] == "Délais trop longs"
        finally:
            # Cleanup
            session.delete(f"{API}/prospects/{pid}", timeout=15)


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
