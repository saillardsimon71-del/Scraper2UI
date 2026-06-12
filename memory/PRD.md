# PRD — Cockpit Prospection (Scraper2UI)

## Problème d'origine
Porter un scraper CLI Python (prospection artisans français) en application web full-stack : scraping multi-sources, enrichissement, scoring, séquences de relance multicanal, envoi d'emails automatisé (SendGrid) et webhooks (réponses, bounces, désabonnements).

## Stack
React (CRA) + Shadcn UI · FastAPI · MongoDB · SendGrid (envoi + inbound parse).
Fichiers clés : `backend/server.py` (API), `backend/scraper_core.py` (sources/enrichissement/audit), `backend/prospection.py` (canaux, scénarios, rendu), `backend/autopilot.py` (envoi auto), `backend/webhook.py`.

## Règles métier centrales
- **Canal unique par séquence** (décision utilisateur it. 9, annule la rotation multi-canal d'it. 8) : canal choisi à la création par priorité **Email > WhatsApp (mobile 06/07) > LinkedIn > Téléphone (fixe)** — toute la séquence (4 étapes) reste dessus. Aucun contact → prospect non ajouté.
- `plan_canaux` (liste uniforme) + `canal_contact` conservés techniquement (advance_updates les maintient) ; recalculés sur PATCH seulement si jamais contacté.
- Prospects canal **email = 100 % pilote automatique** ; whatsapp/linkedin/téléphone = file du jour.
- **File du jour triée par score_vendabilite desc** (puis score_conversion, created_at).
- **A/B testing objets email** : chaque étape a `objet` (A) + `objet_b` (B) ; `variante_ab` assignée 50/50 à la création du prospect ; envois historisés avec `variante` + `objet_template` pour les stats.
- Statut "À contacter" pendant toute la séquence ; passe à répondu/opt-out/épuisé selon événements.
- Templates v3 (SCENARIO_VERSION=3) : plus de « c'est Simon » / « Simon ici » ; variable `{argument_vente}` = 1ʳᵉ raison de vendabilité (fallback pitch → signal) injectée dans les messages.

## Implémenté (historique)
- It. 1-4 (forks précédents) : scraping (gouv/OSM), audit + scoring, pipeline kanban, file du jour, import Excel/CSV, export, séquences éditables, autopilot SendGrid, webhooks (réponses/bounces/opt-out), paramètres.
- It. 5 (11/06/2026) : canal unique par prospect + templates neutres + migration (suppression sans-contact) + file du jour filtrée + autopilot par canal.
- It. 6 (11/06/2026) :
  - Fallback miroirs Overpass OSM (overpass-api.de → maps.mail.ru → kumi) — overpass-api.de bloqué depuis le pod.
  - Colonnes Canal (icônes) + Séquence ("en cours · 2/4") dans Prospects.
  - Historique enrichi : objet + message stockés à chaque envoi (auto + manuel), dépliables au clic dans la fiche prospect (backfill effectué).
  - Scraper multi-sélection : métiers (chips) × villes (tags), recherches croisées dans un job, limite par recherche.
  - Enrichissement contact découplé de l'audit (téléphone + email cherchés systématiquement).
  - **Module email** : `enrich_email()` visite site + pages contact/mentions légales, privilégie email du domaine. Intégré au scraping + bouton "Trouver les emails manquants" (job backfill, 64 emails trouvés sur 123 → 88/152 avec email).
  - **Vérification WhatsApp** : `is_mobile_fr()` (phonenumbers) — canal whatsapp réservé aux mobiles 06/07. Constat réel : 11 mobiles / 64.
  - **Canal téléphone** (choix utilisateur) : fixes sans autre contact → canal "telephone", bouton Appeler (tel:) dans file du jour + fiche. 53 prospects reclassés.
  - **Fix bouton WhatsApp** : wa_link passe de wa.me (redirige vers api.whatsapp.com bloqué) à `web.whatsapp.com/send?phone=&text=`.
- It. 7 (12/06/2026, fork) : dashboard **Business** (entonnoir, CA, raisons de refus, conversion par profil) + score de **vendabilité** (`compute_site_vendabilite` : score/label/raisons/pitch) + actions CRM gagné(CA)/perdu(raison)/rappel.
- It. 8 (12/06/2026) — « Machine de guerre » (5 axes, testée 25/25 backend + UI 100%) :
  - File du jour triée par vendabilité (affichage score « vendable » + badge label·score).
  - Dashboard Business : **Performance par canal**, **par étape**, **A/B testing** (cartes A/B + table top objets). Attribution : une réponse est créditée au dernier envoi qui la précède (calcul Python sur l'historique dans GET /api/dashboard/business).
  - **A/B objets email** : `objet_b` par étape (éditable page Séquences), `variante_ab` par prospect, tracking `variante`/`objet_template` dans historique + email_log (autopilot + action manuelle).
  - **Séquences multi-canal** : `canal_plan()` / `available_canaux()` dans prospection.py, `plan_canaux` par prospect, bascule de canal dans `advance_updates`, aperçu séquence par étape (canal + objet rendu) dans la fiche, migration idempotente `migrate_multicanal()` (135 prospects migrés).
  - **Injection vendabilité** : `{argument_vente}` dans les templates site_ancien/site_moyen.
  - Templates v3 sans « c'est Simon » / « Simon ici » / « à nouveau » (demande utilisateur explicite) ; tests régression `backend/tests/test_machine_guerre.py` + `test_iteration5_api.py`.
- It. 9 (12/06/2026) : **retour au canal unique** à la demande de l'utilisateur (« quand une séquence démarre, elle fait tout sur le même canal »). `canal_plan()` retourne désormais [canal_prioritaire] × n_etapes ; migration idempotente réaligne les plans à rotation résiduels ; le reste d'it. 8 (vendabilité, A/B, stats) est conservé.

## Backlog priorisé
- P1 : digest quotidien par email (résumé du soir : envois, réponses, intéressés, file de demain)
- P2 : vraie vérification WhatsApp via Baileys (QR code, refusée pour l'instant — filtre mobile jugé suffisant)
- P2 : sync Google Sheets ; PDF audit ; rate limiting IA ; redaction clés API dans GET /settings
- P2 : fallback non-drag&drop kanban ; warnings a11y Dialog ; découpage server.py en modules (~1690 lignes — routes settings/scenarios/import/IA à extraire) ; debounce quota autopilot
- P3 : conclusion automatique du test A/B (bascule sur la variante gagnante après N envois significatifs)

## Notes techniques
- Migration one-shot flag `settings.migration_canal_unique` (déjà exécutée).
- Jobs génériques dans `db.jobs` (scrape + enrich_emails), polling via GET /api/scrape/jobs/{id}.
- SendGrid key + settings dans document `settings._id="global"` en Mongo.
- La preview gateway peut être en veille pour le navigateur d'automatisation : tester l'UI via http://localhost:3000.
