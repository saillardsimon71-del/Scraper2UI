"""Tests d'intégration API — itération 5 (machine de guerre).

Vérifie via le backend réel (REACT_APP_BACKEND_URL) :
- GET /api/queue trié par vendabilité décroissante
- GET /api/dashboard/business avec par_canal/par_etape/ab_objets/top_objets
- GET /api/scenarios v3 + objet_b non vide + pas de « Simon ici »
- PUT /api/scenarios persiste objet_b
- POST /api/import (CSV mobile+email) → plan multi-canal + variante_ab
- POST /api/prospects/{id}/action « envoye » 2x → bascule canal email→whatsapp,
  historique avec canal/variante/objet_template
- GET /api/prospects/{id}.sequence (canal par étape + objet)
- PATCH /api/prospects/{id} recalcule plan_canaux si tel change
- {argument_vente} rendu dans le message d'un prospect site_ancien
- Régression : /api/dashboard/stats, /api/prospects, actions gagne/perdu/rappel
"""
import copy
import io
import os
import time

import pytest
import requests
from dotenv import load_dotenv

# Charge l'URL backend depuis frontend/.env (single source of truth)
_FRONTEND_ENV = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
load_dotenv(_FRONTEND_ENV)
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL manquant"
API = f"{BASE_URL}/api"

# IDs créés pour cleanup
CREATED_IDS: list[str] = []


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    yield s
    # Cleanup
    for pid in CREATED_IDS:
        try:
            s.delete(f"{API}/prospects/{pid}", timeout=10)
        except Exception:
            pass


def _import_csv(session, csv: str, filename="test.csv"):
    files = {"file": (filename, io.BytesIO(csv.encode("utf-8")), "text/csv")}
    return session.post(f"{API}/import", files=files, timeout=20)


def _find_by_entreprise(session, name: str) -> dict | None:
    r = session.get(f"{API}/prospects", params={"q": name, "limit": 5}, timeout=10)
    assert r.status_code == 200
    for p in r.json().get("items", []):
        if p.get("entreprise") == name:
            return p
    return None


# -------------------- 1) Queue triée par vendabilité

def test_queue_sorted_by_vendabilite(session):
    # Crée 2 prospects manuels (whatsapp) avec scores vendabilité différents
    name_lo = "TEST_ITER5_QueueLo"
    name_hi = "TEST_ITER5_QueueHi"
    # Hi : pas de site_web (score_vendabilite très haut, profil pas_de_site)
    # Lo : site_web bidon mais note basse -> score plus bas mais > 0
    csv = (
        "entreprise;metier;ville;telephone;email;site_web\n"
        f"{name_lo};plombier;Lyon;06 11 11 11 11;;https://exemple-lo.fr\n"
        f"{name_hi};plombier;Lyon;06 22 22 22 22;;\n"
    )
    r = _import_csv(session, csv)
    assert r.status_code == 200, r.text
    p_lo = _find_by_entreprise(session, name_lo)
    p_hi = _find_by_entreprise(session, name_hi)
    assert p_lo and p_hi
    CREATED_IDS.extend([p_lo["id"], p_hi["id"]])

    # Queue
    r = session.get(f"{API}/queue", params={"limit": 100}, timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    # Récupère les positions
    positions = {}
    for i, it in enumerate(items):
        eid = it["prospect"]["entreprise"]
        if eid in (name_lo, name_hi):
            positions[eid] = i
    assert name_hi in positions and name_lo in positions, f"Prospects pas dans la queue : {positions}"
    assert positions[name_hi] < positions[name_lo], (
        f"Hi (sans site) doit être avant Lo. Hi={positions[name_hi]} Lo={positions[name_lo]}"
    )


# -------------------- 2) Dashboard business : nouveaux champs

def test_dashboard_business_new_fields(session):
    r = session.get(f"{API}/dashboard/business", timeout=15)
    assert r.status_code == 200
    data = r.json()
    for key in ("par_canal", "par_etape", "ab_objets", "top_objets"):
        assert key in data, f"Champ manquant : {key}"
    assert isinstance(data["par_canal"], dict)
    assert isinstance(data["par_etape"], list)
    assert "A" in data["ab_objets"] and "B" in data["ab_objets"]
    for v in ("A", "B"):
        ab = data["ab_objets"][v]
        for k in ("envois", "reponses", "taux"):
            assert k in ab, f"ab_objets[{v}].{k} manquant"
    assert isinstance(data["top_objets"], list)
    # par_etape entries doivent contenir etape/envois/reponses/taux
    for e in data["par_etape"]:
        assert {"etape", "envois", "reponses", "taux"}.issubset(e.keys())


# -------------------- 3) Scénarios v3 + objet_b + pas de Simon ici

INTERDITS = ("c'est {prenom_exp}", "{prenom_exp} ici", "{prenom_exp} à nouveau")


def test_scenarios_v3_and_no_simon_ici(session):
    r = session.get(f"{API}/scenarios", timeout=10)
    assert r.status_code == 200
    scs = r.json()["scenarios"]
    assert len(scs) == 4
    for sc in scs:
        assert sc.get("version", 0) >= 3, f"{sc['profil']} version={sc.get('version')}"
        for e in sc["etapes"]:
            assert e.get("objet"), f"{sc['profil']} étape {e['etape']} sans objet"
            assert e.get("objet_b"), f"{sc['profil']} étape {e['etape']} sans objet_b"
            for champ in ("template", "template_court"):
                txt = e.get(champ, "") or ""
                for interdit in INTERDITS:
                    assert interdit not in txt, (
                        f"« {interdit} » dans {sc['profil']}/étape {e['etape']}/{champ}"
                    )


# -------------------- 4) PUT /api/scenarios persiste objet_b

def test_put_scenario_persists_objet_b(session):
    # Backup site_moyen
    r = session.get(f"{API}/scenarios", timeout=10)
    orig = next(sc for sc in r.json()["scenarios"] if sc["profil"] == "site_moyen")
    backup = copy.deepcopy(orig)

    try:
        # Modif étape 1 — change objet_b
        modif = copy.deepcopy(orig)
        modif["etapes"][0]["objet_b"] = "TEST_ITER5_OBJET_B"
        payload = {"etapes": modif["etapes"]}
        r = session.put(f"{API}/scenarios/site_moyen", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        # Vérif persistance
        r = session.get(f"{API}/scenarios", timeout=10)
        sc = next(x for x in r.json()["scenarios"] if x["profil"] == "site_moyen")
        assert sc["etapes"][0]["objet_b"] == "TEST_ITER5_OBJET_B"
    finally:
        # Restore
        session.put(f"{API}/scenarios/site_moyen",
                    json={"etapes": backup["etapes"]}, timeout=15)


# -------------------- 5) POST /api/import : prospect mobile+email = multi-canal

def test_import_creates_multicanal_prospect(session):
    name = "TEST_ITER5_Multi"
    csv = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name};couvreur;Marseille;06 33 33 33 33;multi@example.test\n"
    )
    r = _import_csv(session, csv)
    assert r.status_code == 200, r.text
    p = _find_by_entreprise(session, name)
    assert p, "Prospect non créé"
    CREATED_IDS.append(p["id"])
    assert p["plan_canaux"] == ["email", "email", "whatsapp", "email"], p["plan_canaux"]
    assert p["canal_contact"] == "email"
    assert p["variante_ab"] in ("A", "B"), p.get("variante_ab")


# -------------------- 6) Multi-canal : 2 actions envoye → étape 3 + bascule whatsapp

def test_multi_canal_two_sends_then_whatsapp(session):
    name = "TEST_ITER5_Bascule"
    csv = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name};electricien;Nice;06 44 44 44 44;bascule@example.test\n"
    )
    assert _import_csv(session, csv).status_code == 200
    p = _find_by_entreprise(session, name)
    assert p
    CREATED_IDS.append(p["id"])
    pid = p["id"]

    # Send 1
    r = session.post(f"{API}/prospects/{pid}/action", json={"type": "envoye"}, timeout=10)
    assert r.status_code == 200
    p1 = r.json()
    assert p1["etape_relance"] == 2
    assert p1["canal_contact"] == "email"  # étape 2 = email

    # Send 2
    r = session.post(f"{API}/prospects/{pid}/action", json={"type": "envoye"}, timeout=10)
    assert r.status_code == 200
    p2 = r.json()
    assert p2["etape_relance"] == 3
    assert p2["canal_contact"] == "whatsapp", f"Attendu whatsapp, got {p2['canal_contact']}"

    # Historique : 2 events 'envoye' avec canal=email, variante, objet_template
    sends = [h for h in p2.get("historique", []) if h.get("type") == "envoye"]
    assert len(sends) == 2
    for h in sends:
        assert h.get("canal") == "email"
        assert h.get("variante") in ("A", "B"), h
        assert h.get("objet_template"), f"objet_template manquant : {h}"


# -------------------- 7) GET /api/prospects/{id}.sequence

def test_prospect_sequence_has_canal_and_objet(session):
    name = "TEST_ITER5_Sequence"
    csv = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name};peintre;Paris;06 55 55 55 55;seq@example.test\n"
    )
    assert _import_csv(session, csv).status_code == 200
    p = _find_by_entreprise(session, name)
    assert p
    CREATED_IDS.append(p["id"])
    r = session.get(f"{API}/prospects/{p['id']}", timeout=10)
    assert r.status_code == 200
    item = r.json()
    seq = item.get("sequence")
    assert isinstance(seq, list) and len(seq) >= 4
    # plan_canaux attendu : email/email/whatsapp/email
    expected = ["email", "email", "whatsapp", "email"]
    actual = [s["canal"] for s in seq[:4]]
    assert actual == expected, f"Sequence canaux : attendu {expected}, got {actual}"
    # étapes email ont un champ 'objet'
    for s in seq:
        if s["canal"] == "email":
            assert s.get("objet"), f"objet manquant pour étape email {s['etape']}"


# -------------------- 8) PATCH recalcule plan_canaux si tel change (jamais contacté)

def test_patch_recomputes_plan_canaux(session):
    name = "TEST_ITER5_Patch"
    csv = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name};menuisier;Toulouse;;patch@example.test\n"
    )
    assert _import_csv(session, csv).status_code == 200
    p = _find_by_entreprise(session, name)
    assert p
    CREATED_IDS.append(p["id"])
    # Initial : email seul (pas de tel)
    assert p["plan_canaux"] == ["email"] * 4

    # PATCH avec un mobile
    r = session.patch(f"{API}/prospects/{p['id']}",
                      json={"telephone": "06 77 77 77 77"}, timeout=10)
    assert r.status_code == 200, r.text
    p2 = r.json()
    assert p2["plan_canaux"] == ["email", "email", "whatsapp", "email"], p2["plan_canaux"]
    assert p2["canal_contact"] == "email"


# -------------------- 9) {argument_vente} rendu (site_ancien)

def test_argument_vente_rendered_in_sequence(session):
    name = "TEST_ITER5_ArgVente"
    # site_ancien : note_site basse + site_web présent → profil site_ancien
    csv = (
        "entreprise;metier;ville;telephone;email;site_web;note_site\n"
        f"{name};plombier;Bordeaux;;argvente@example.test;https://vieux-site.fr;30\n"
    )
    assert _import_csv(session, csv).status_code == 200
    p = _find_by_entreprise(session, name)
    assert p
    CREATED_IDS.append(p["id"])
    r = session.get(f"{API}/prospects/{p['id']}", timeout=10)
    assert r.status_code == 200
    item = r.json()
    # Au moins un des messages de la séquence doit contenir l'argument rendu et pas la variable brute
    seq_msgs = " || ".join(s.get("message", "") for s in item.get("sequence", []))
    main_msg = item.get("message", "")
    combined = f"{main_msg} || {seq_msgs}".lower()
    assert "{argument_vente}" not in combined, "Variable brute {argument_vente} non rendue !"
    # Doit contenir une trace de raison (raisons_vendabilite généralement contient 'site' ou 'note')
    raisons = p.get("raisons_vendabilite") or []
    assert raisons, f"Pas de raisons_vendabilite calculées pour {name}"
    # Au moins une raison apparaît dans un des messages (cas insensible)
    found = any(any(r.lower() in combined for r in raisons) for _ in [0])
    # Vérification plus souple : la profil doit être site_ancien et la 1ère étape doit avoir injecté qq chose
    assert p.get("profil") == "site_ancien", f"profil={p.get('profil')}"
    assert found or any(token in combined for token in ("obsolète", "obsolete", "/100", "vieux", "ancien")), (
        f"Argument de vente non détecté dans messages. raisons={raisons} msg={combined[:300]}"
    )


# -------------------- 10) Régression : stats / prospects / actions

def test_regression_dashboard_stats(session):
    r = session.get(f"{API}/dashboard/stats", timeout=10)
    assert r.status_code == 200
    d = r.json()
    for k in ("total", "file_du_jour", "envoyes_aujourdhui", "repondus", "contactes",
              "taux_reponse", "par_statut", "par_niveau"):
        assert k in d


def test_regression_list_prospects(session):
    r = session.get(f"{API}/prospects", params={"limit": 5}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and "total" in d


def test_regression_actions_gagne_perdu_rappel(session):
    # Crée un prospect dédié à ces actions
    name = "TEST_ITER5_Actions"
    csv = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name};plombier;Lille;06 88 88 88 88;actions@example.test\n"
    )
    assert _import_csv(session, csv).status_code == 200
    p = _find_by_entreprise(session, name)
    assert p
    pid = p["id"]
    CREATED_IDS.append(pid)

    # rappel
    r = session.post(f"{API}/prospects/{pid}/action",
                     json={"type": "rappel", "rappel_dans_jours": 5}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("date_rappel")

    # gagne avec ca
    r = session.post(f"{API}/prospects/{pid}/action",
                     json={"type": "gagne", "ca_contrat": 1200}, timeout=10)
    assert r.status_code == 200
    pg = r.json()
    assert pg["statut"] == "gagne"
    assert pg.get("ca_contrat") == 1200

    # Crée un autre pour 'perdu'
    name2 = "TEST_ITER5_Perdu"
    csv2 = (
        "entreprise;metier;ville;telephone;email\n"
        f"{name2};plombier;Lille;06 99 99 99 99;perdu@example.test\n"
    )
    assert _import_csv(session, csv2).status_code == 200
    p2 = _find_by_entreprise(session, name2)
    assert p2
    CREATED_IDS.append(p2["id"])
    r = session.post(f"{API}/prospects/{p2['id']}/action",
                     json={"type": "perdu", "raison_refus": "Pas le moment"}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("raison_refus") == "Pas le moment"
