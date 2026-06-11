"""Iteration 2 backend tests: scenario-stats, export Excel, mini-audit, email/send, scenarios email channel."""
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ============================= Scenario stats
class TestScenarioStats:
    def test_scenario_stats_shape(self, session):
        r = session.get(f"{API}/dashboard/scenario-stats", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "stats" in data
        stats = data["stats"]
        assert len(stats) == 4, f"expected 4 profils, got {len(stats)}"
        profils = {s["profil"] for s in stats}
        assert profils == {"pas_de_site", "site_ancien", "signal_chaud", "site_moyen"}
        for s in stats:
            for k in ("label", "total", "contactes", "repondus", "rdv", "taux_reponse"):
                assert k in s, f"missing {k} in {s}"
            assert isinstance(s["taux_reponse"], (int, float))


# ============================= Export Excel
class TestExportExcel:
    def test_export_returns_xlsx(self, session):
        r = session.get(f"{API}/export/prospects", timeout=60)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "spreadsheetml" in ct or "xlsx" in ct, f"unexpected content-type: {ct}"
        # check first bytes are XLSX magic (PK = zip)
        assert r.content[:2] == b"PK", "Response is not a valid xlsx (no PK header)"
        cd = r.headers.get("content-disposition", "")
        assert ".xlsx" in cd

    def test_export_with_filter(self, session):
        r = session.get(f"{API}/export/prospects?statut=a_contacter", timeout=60)
        assert r.status_code == 200
        assert r.content[:2] == b"PK"


# ============================= Mini-audit AI (real call - one shot only)
class TestMiniAudit:
    def test_mini_audit_generates_clean_text(self, session):
        # find a prospect with a site to test full path
        plist = session.get(f"{API}/prospects?limit=20", timeout=15).json()
        assert plist["items"], "Need at least one prospect in DB"
        # prefer one with a site_web
        target = next((p for p in plist["items"] if p.get("site_web") and p["site_web"] != "Pas de site"), plist["items"][0])
        pid = target["id"]

        r = session.post(f"{API}/ai/mini-audit", json={"prospect_id": pid}, timeout=90)
        assert r.status_code == 200, f"mini-audit failed: {r.status_code} {r.text}"
        d = r.json()
        assert "mini_audit" in d
        audit = d["mini_audit"]
        assert isinstance(audit, str) and len(audit) > 30

        # Strip the lien_rdv (calendly https://...) before jargon check (link is legitimate)
        import re as _re
        sanitized = _re.sub(r"https?://\S+", "", audit).lower()
        # /100 must not appear at all - score-free
        assert "/100" not in audit, f"contains note /100: {audit}"
        # no SEO/HTTPS/SSL/etc jargon in human-readable portion
        for term in ["seo", "https", "ssl", "viewport", "balise ", " cms", "referencement", "responsive"]:
            assert term not in sanitized, f"contient jargon technique '{term}': {audit}"

        # verify stored on prospect
        r2 = session.get(f"{API}/prospects/{pid}", timeout=15)
        assert r2.status_code == 200
        # mini_audit is stored on prospect object inside queue-style response
        prospect_obj = r2.json().get("prospect", {})
        assert prospect_obj.get("mini_audit") == audit, "mini_audit not persisted on prospect"


# ============================= Email send (no SendGrid config -> 400)
class TestEmailSend:
    def test_email_send_without_config_returns_400(self, session):
        plist = session.get(f"{API}/prospects?limit=5", timeout=15).json()
        assert plist["items"]
        pid = plist["items"][0]["id"]

        # Ensure no sendgrid key in settings (don't overwrite if present though)
        cur = session.get(f"{API}/settings", timeout=15).json()
        had_key = bool(cur.get("sendgrid_api_key"))
        had_sender = bool(cur.get("email_expediteur"))
        if had_key or had_sender:
            pytest.skip("SendGrid is configured; skipping no-config test")

        r = session.post(f"{API}/email/send", json={
            "prospect_id": pid, "subject": "Test", "message": "hello"}, timeout=15)
        assert r.status_code == 400, r.text
        body = r.json()
        # Could be {detail: "SENDGRID_NON_CONFIGURE"} from HTTPException
        msg = body.get("detail") or body.get("message") or str(body)
        assert "SENDGRID_NON_CONFIGURE" in msg, f"unexpected error: {body}"


# ============================= Scenarios with email channel
class TestScenarioEmailChannel:
    def test_scenario_accepts_email_channel_with_objet(self, session):
        # Get current scenario for pas_de_site
        r = session.get(f"{API}/scenarios", timeout=15)
        assert r.status_code == 200
        scenarios = {s["profil"]: s for s in r.json()["scenarios"]}
        original = scenarios["pas_de_site"]
        original_etapes = [dict(e) for e in original["etapes"]]

        # Modify first step to use email channel + objet
        new_etapes = [dict(e) for e in original_etapes]
        new_etapes[0] = {
            "etape": 1,
            "delai_jours": new_etapes[0]["delai_jours"],
            "canal": "email",
            "template": "Bonjour {entreprise}, suite à mon analyse...\nCordialement, {prenom_exp}",
            "objet": f"TEST_OBJET_{uuid.uuid4().hex[:6]} pour {{entreprise}}",
        }

        r = session.put(f"{API}/scenarios/pas_de_site", json={"etapes": new_etapes}, timeout=15)
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["etapes"][0]["canal"] == "email"
        assert saved["etapes"][0]["objet"].startswith("TEST_OBJET_")

        # Verify persistence
        r2 = session.get(f"{API}/scenarios", timeout=15)
        sc = {s["profil"]: s for s in r2.json()["scenarios"]}["pas_de_site"]
        assert sc["etapes"][0]["canal"] == "email"
        assert "TEST_OBJET_" in sc["etapes"][0]["objet"]

        # The queue should render messages for prospects with pas_de_site profil
        q = session.get(f"{API}/queue?limit=200", timeout=15).json()
        # at least find a pas_de_site prospect with rendered message (any canal accepted)
        pds_items = [it for it in q["items"] if it["prospect"].get("profil") == "pas_de_site"]
        if pds_items:
            it = pds_items[0]
            assert "{entreprise}" not in it["message"], f"variable non rendue: {it['message']}"

        # Restore - put back original
        r = session.put(f"{API}/scenarios/pas_de_site",
                        json={"etapes": original_etapes}, timeout=15)
        assert r.status_code == 200


# ============================= Settings: SendGrid/email_expediteur persistence
class TestSettingsSendGrid:
    def test_sendgrid_fields_persist(self, session):
        old = session.get(f"{API}/settings", timeout=15).json()
        new_sender = "TEST_simon_" + uuid.uuid4().hex[:6] + "@example.com"
        r = session.put(f"{API}/settings", json={"email_expediteur": new_sender}, timeout=15)
        assert r.status_code == 200
        assert r.json()["email_expediteur"] == new_sender
        # verify get
        got = session.get(f"{API}/settings", timeout=15).json()
        assert got["email_expediteur"] == new_sender
        assert "sendgrid_api_key" in got
        # restore (avoid leaking test email)
        session.put(f"{API}/settings", json={"email_expediteur": old.get("email_expediteur") or ""}, timeout=15)
