# PRD — Cockpit Prospection (port web de Scraper2UI)

## Problème initial
Porter le repo GitHub `saillardsimon71-del/Scraper2UI` (outil Python de prospection d'artisans FR) en web app complète, avec pour objectif d'automatiser la prospection LinkedIn/WhatsApp en semi-auto : l'utilisateur n'a plus qu'à cliquer "envoyer" avec des messages/liens préparés et personnalisés selon scénarios.

## Choix utilisateur (11/06/2026)
- Port complet scraper + cockpit en web app
- Prospects via import Excel/CSV des exports du scraper (+ scraping intégré)
- Messages : templates avec variables + amélioration IA optionnelle (Emergent LLM key, GPT-5)
- Séquences de relance par profil : pas de site / site ancien / signal chaud (+ site moyen)
- Desktop-first, interface en français

## Architecture
- **Backend** FastAPI (port 8001) + MongoDB : `server.py` (routes), `scraper_core.py` (sources gouv/OSM/Serper, audit site /100, signaux d'achat, scoring conversion — porté du repo), `prospection.py` (scénarios par défaut, profils, rendu des messages)
- **Frontend** React + shadcn + Phosphor Icons, design "Swiss high-contrast" (sidebar noire, accents #002FA7 / WhatsApp vert / LinkedIn bleu)
- **IA** : `emergentintegrations` LlmChat, openai `gpt-5` (env `AI_MODEL`), clé EMERGENT_LLM_KEY dans backend/.env

## Implémenté (11/06/2026) — MVP complet, testé (iteration_1 : 9/10 backend, bug IA corrigé)
- File du jour : prospects dus triés par score, message rendu, lien wa.me pré-rempli, lien LinkedIn + copie message, marquer envoyé / skip / détail
- Pipeline statuts : a_contacter → envoyé (relance auto-planifiée selon séquence) → repondu/rdv/gagne/perdu/opt_out/epuise + réactivation
- Scraper : jobs en arrière-plan (gouv + OSM), enrichissement téléphone, audit site /100, signaux d'achat, scoring 0-100, dédoublonnage (siren/tel/nom+ville)
- Serper optionnel (clé dans Paramètres) pour trouver les sites manquants via Google
- Import CSV/Excel avec mapping de colonnes flexible (accents ignorés) + dédoublonnage
- Séquences éditables : 4 profils × 3 étapes (canal, délai J+, template avec variables {entreprise} {ville} {signal} {note_site} {prenom_exp} {lien_rdv}…)
- Sheet détail prospect : audit, signaux, message éditable, amélioration IA, séquence complète, historique
- Paramètres : prénom expéditeur, lien RDV, clé Serper

## Implémenté — Itération 2 (11/06/2026), testé (iteration_2 : backend 100%, bug generateMiniAudit corrigé + vérifié)
- Export Excel des prospects (filtres respectés) — bouton sur page Prospects
- Canal email : SendGrid (clé + sender dans Paramètres, fallback mailto sans clé), étapes de séquence avec canal email + objet, bouton email dans la file du jour
- Vue Pipeline kanban (drag & drop entre statuts) + stats de réponse par scénario (contactés/réponses/RDV/taux par profil)
- Mini-audit IA conversion-friendly (sans note, sans jargon technique, bénéfices client concrets, lien Calendly intégré) — généré depuis la fiche prospect, stocké, copiable, envoyable sur WhatsApp en 1 clic, inclus dans l'export Excel
- Settings configurés : prenom_expediteur=Simon, lien_rdv=https://calendly.com/sitequivend/30min

## Implémenté — Itération 3 (11/06/2026) : Pilote automatique emails (porté du scraper de base), testé e2e (envoi réel SendGrid réussi)
- `backend/autopilot.py` : boucle de fond (toutes les 5 min) qui envoie automatiquement les étapes **email** des séquences aux prospects dus (relances auto incluses), porté du `campaign_manager.py` du repo Scraper
- Garde-fous : quota journalier (50 par défaut), plage horaire Europe/Paris (9h–18h), jours ouvrés, arrêt auto si répondu/opt-out (statut pipeline), footer désinscription "répondez STOP"
- Endpoints : `GET /api/autopilot/status`, `POST /api/autopilot/run` (passage manuel forcé), `GET /api/autopilot/log` ; settings étendus (autopilot_actif, quota, heures, jours ouvrés)
- Journal des envois persisté dans `db.email_log` (auto + manuels) ; historique prospect type "envoye" canal "email" auto=True (compté dans les stats)
- Séquences par défaut : étape 4 **email** ajoutée aux 4 profils (objet + template longs, variables incluses)
- Frontend : carte "Pilote automatique" dans Paramètres (`AutopilotCard.jsx`) — interrupteur ACTIF/INACTIF, badges quota/en attente/raison de pause, réglages, bouton "Lancer un passage maintenant", journal des 20 derniers envois
- Refactor : `advance_updates()` partagé (action manuelle "envoyé" + autopilot) ; `send_email_sync` mutualisé
- Config : clé SendGrid + expéditeur simon@sitequivend.fr enregistrés, pilote ACTIVÉ, lien_rdv Calendly restauré
- Test réel : email envoyé avec succès via SendGrid à simon@sitequivend.fr (statut 202), séquence avancée → épuisé, log OK

## Implémenté — Itération 4 (11/06/2026) : Webhook SendGrid (porté du scraper de base), testé e2e
- `backend/webhook.py` : routeur `/api/webhook/*` sécurisé par token secret (?token=…, généré au démarrage, dans settings.webhook_token)
- **Inbound Parse** (`POST /api/webhook/sendgrid/inbound`) : réception des réponses email, classement auto par mots-clés (STOP/désabonner → opt_out ; oui/intéressé/rdv → repondu+interesse ; sinon repondu), mise à jour prospect + historique, stockage db.reponses, transfert de chaque réponse vers la boîte de l'expéditeur via SendGrid
- **Event Webhook** (`POST /api/webhook/sendgrid/events`) : bounce/dropped → email_invalide=True (exclu de l'autopilot) ; spamreport/unsubscribe → opt_out ; stockage db.email_events
- `GET /api/webhook/reponses` : liste des réponses reçues
- **Reply-To** : setting email_reponse (ex simon@reponse.sitequivend.fr) appliqué aux envois autopilot + manuels
- Frontend : carte "Webhook SendGrid" dans Paramètres (`WebhookCard.jsx`) — URLs à copier (avec token), champ adresse de réponse, instructions DNS (MX reponse.sitequivend.fr → mx.sendgrid.net), liste des réponses reçues
- Tests e2e validés : 401 mauvais token, réponse intéressée → repondu, STOP → opt_out, bounce → email_invalide ; nettoyage fait
- ⚠️ Action utilisateur requise : configurer chez SendGrid l'Inbound Parse + l'Event Webhook avec les URLs affichées dans Paramètres, et créer l'enregistrement DNS MX du sous-domaine de réponse

## Implémenté — Itération 5 (11/06/2026) : Canal unique par prospect (priorité Email > WhatsApp > LinkedIn), testé e2e
- `determine_canal()` dans prospection.py : à la création (scraping/import), canal fixé par priorité — email → "email", sinon téléphone → "whatsapp", sinon linkedin_url → "linkedin", sinon prospect NON ajouté (compteur "sans_contact" affiché dans Scraper + Import)
- Toute la séquence (étape 1 → dernière relance) reste sur le même canal ; plus de canal par étape (champ `canal` retiré d'EtapeModel et des scénarios)
- Templates des 4 profils réécrits en neutres (aucune référence au canal) + objet d'email à chaque étape (utilisé seulement si canal email)
- Pilote automatique : gère désormais TOUTE la séquence des prospects `canal_contact: "email"` (requête sur le prospect, plus sur l'étape)
- File du jour (`/api/queue` + dashboard file_du_jour) : uniquement canaux whatsapp/linkedin (les emails sont 100% autopilot) ; un seul bouton d'action par ligne selon le canal
- PATCH prospect : canal recalculé si email/téléphone/linkedin modifiés ET séquence pas encore démarrée ; figé dès le premier envoi
- Migration one-shot au démarrage (flag settings.migration_canal_unique) : scénarios remplacés, 3 prospects sans contact supprimés, canal_contact affecté à tous
- Frontend : Scenarios.jsx (bandeau explicatif, plus de sélecteur de canal, objet toujours visible), FileDuJour.jsx (bouton unique par canal, envoi email manuel retiré), ProspectSheet.jsx (boutons selon canal, note "géré par le pilote" si email), AutopilotCard texte mis à jour, export Excel colonne "Canal"
- Tests e2e curl : priorité email>wa>li ✓, sans contact ignoré ✓, queue filtrée ✓, autopilot en_attente ✓, recalcul/figeage du canal ✓ ; UI Séquences vérifiée par screenshot

## Backlog priorisé
- P1 : digest quotidien par email (résumé du soir : envois, réponses, intéressés)
- P2 : sync Google Sheets ; PDF audit ; rate limiting IA ; redaction clés API dans GET /settings
- P2 : fallback non-drag&drop sur kanban (sélecteur de statut sur carte)
- P2 : warnings a11y DialogTitle/Description ; découpage de server.py en modules ; debounce sur input quota autopilot

## Notes techniques
- API gouv (recherche-entreprises.api.gouv.fr) : gratuite sans clé. OSM/Overpass : gratuit, parfois lent.
- Pas d'authentification (outil personnel mono-utilisateur).
- Délais de relance = jours après l'étape précédente (étape 1 immédiate).
