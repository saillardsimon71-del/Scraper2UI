# Cockpit Prospection (Scraper2UI)

Application full-stack de prospection : scraping multi-sources (data.gouv, OSM), enrichissement, scoring,
séquences de relance multicanal (email / WhatsApp / LinkedIn / téléphone), envoi automatisé via SendGrid,
webhooks (réponses, bounces, opt-out).

Stack : **React (CRA) + FastAPI + MongoDB + SendGrid**.

---

## Lancer hors d'Emergent (auto-hébergement)

### Pré-requis
- Docker + Docker Compose (Docker Desktop sur Mac/Windows, ou docker.io + docker-compose-plugin sur Linux)
- ~2 Go de RAM disponibles

### Installation

```bash
# 1) Clone le repo
git clone https://github.com/saillardsimon71-del/Scraper2UI.git
cd Scraper2UI

# 2) Configure
cp .env.example .env
# Édite .env si besoin (PUBLIC_URL si tu mets l'app derrière un nom de domaine)

# 3) Build + démarre tous les services
docker compose up -d --build

# 4) Vérifie que tout tourne
docker compose ps
docker compose logs -f backend
```

L'application est accessible sur **http://localhost:8080**.

### Arrêter / redémarrer
```bash
docker compose stop      # arrête (les données restent)
docker compose start     # redémarre
docker compose down      # arrête + supprime les conteneurs (les données restent dans le volume Docker)
docker compose down -v   # ⚠️ supprime AUSSI les données (à éviter)
```

### Persistance des données

Les données Mongo sont stockées dans :
- **Volume Docker nommé** `mongo_data` (survit aux `docker compose down` sans `-v`)
- **Backup JSON** dans `./data/backup/` (synchronisé automatiquement toutes les 5 min) — pratique à committer
  dans un repo Git privé pour une sauvegarde versionnée hors-machine.

### Mise à jour
```bash
git pull
docker compose up -d --build
```

### Premier paramétrage

Va dans **Paramètres** dans l'UI et renseigne :
- Ton prénom (variable `{prenom_exp}` dans les templates)
- Lien de RDV (Calendly, etc.)
- Clé API SendGrid + email expéditeur (vérifié dans SendGrid)
- (Optionnel) Clé Serper.dev pour la recherche Google des sites manquants

### IA d'amélioration de messages

La fonction "Améliorer avec l'IA" est désactivée hors d'Emergent par défaut.
Pour l'activer : renseigne `EMERGENT_LLM_KEY` dans `.env` (clé universelle Emergent).
Sans clé, le reste de l'app fonctionne normalement.

---

## Développement local (sans Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Crée backend/.env avec MONGO_URL, DB_NAME, etc.
uvicorn server:app --reload --port 8001

# Frontend (autre terminal)
cd frontend
yarn install
# Crée frontend/.env avec REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

---

## Architecture

- `backend/server.py` — endpoints FastAPI
- `backend/scraper_core.py` — sources (data.gouv, OSM), enrichissement, audit, scoring
- `backend/prospection.py` — canaux, scénarios, rendu de templates
- `backend/autopilot.py` — envoi automatique des emails programmés
- `backend/webhook.py` — réception webhooks SendGrid (responses, bounces, opt-out)
- `backend/backup.py` — sauvegarde / restauration JSON
- `frontend/src/pages/` — File du jour, Prospects, Pipeline, Scraper, Import, Séquences, Paramètres

## Backup / restauration

- **Automatique** toutes les 5 min dans `data/backup/*.json`
- **Manuel** : page Paramètres → "Sauvegarder maintenant" / "Restaurer depuis le backup"
- **Auto-restore au boot** : si la collection `prospects` est vide ET qu'un backup existe → restauration auto
