# PRD — Cockpit Prospection (Scraper2UI)

## Problème d'origine
Porter un scraper CLI Python (prospection artisans français) en application web full-stack : scraping multi-sources, enrichissement, scoring, séquences de relance multicanal, envoi d'emails automatisé (SendGrid) et webhooks (réponses, bounces, désabonnements).

## Stack
React (CRA) + Shadcn UI · FastAPI · MongoDB · SendGrid (envoi + inbound parse).
Fichiers clés : `backend/server.py` (API), `backend/scraper_core.py` (sources/enrichissement/audit), `backend/prospection.py` (canaux, scénarios, rendu), `backend/autopilot.py` (envoi auto), `backend/webhook.py`.

## Règles métier centrales
- **Canal unique par prospect**, choisi à la création par priorité : **email > whatsapp (mobile 06/07 uniquement) > linkedin > téléphone (fixe)**. Aucun contact → prospect non ajouté (compteur "sans_contact").
- Toute la séquence (4 étapes) reste sur ce canal ; **canal figé dès le premier envoi** (recalculé sur PATCH seulement si jamais contacté).
- Prospects canal **email = 100% pilote automatique** (toutes les étapes). File du jour = actions manuelles whatsapp/linkedin/téléphone uniquement.
- Statut "À contacter" pendant toute la séquence ; passe à répondu/opt-out/épuisé selon événements.
- Templates neutres (sans référence au canal) + objet par étape (utilisé si email). delai_jours = jours après l'étape précédente.

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

## Backlog priorisé
- P1 : digest quotidien par email (résumé du soir : envois, réponses, intéressés, file de demain)
- P2 : vraie vérification WhatsApp via Baileys (QR code, refusée pour l'instant — filtre mobile jugé suffisant)
- P2 : sync Google Sheets ; PDF audit ; rate limiting IA ; redaction clés API dans GET /settings
- P2 : fallback non-drag&drop kanban ; warnings a11y Dialog ; découpage server.py en modules ; debounce quota autopilot

## Notes techniques
- Migration one-shot flag `settings.migration_canal_unique` (déjà exécutée).
- Jobs génériques dans `db.jobs` (scrape + enrich_emails), polling via GET /api/scrape/jobs/{id}.
- SendGrid key + settings dans document `settings._id="global"` en Mongo.
- La preview gateway peut être en veille pour le navigateur d'automatisation : tester l'UI via http://localhost:3000.
