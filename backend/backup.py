"""Sauvegarde / restauration de la base Mongo vers des fichiers JSON.

Objectif : protéger les données contre la réinitialisation du conteneur (pod
Kubernetes éphémère). Les fichiers JSON sont écrits dans `/app/data/backup/`
qui est versionné par Git. L'utilisateur clique "Save to GitHub" pour pousser.
Au démarrage, si la base est vide, on restaure automatiquement.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bson import json_util

logger = logging.getLogger(__name__)

# Collections à sauvegarder (toutes les données métier)
BACKUP_COLLECTIONS = ["prospects", "settings", "scenarios", "email_log", "jobs"]

# Champs sensibles redacted dans le backup (jamais commités sur Git).
# Au restore, ces champs sont ignorés : il faut les ressaisir dans Paramètres
# (depuis backend/.env ou via l'UI) si la base est repartie de zéro.
SENSITIVE_FIELDS = {
    "sendgrid_api_key",
    "serper_api_key",
    "imap_password",
    "webhook_token",  # token de webhook, à régénérer en cas de perte
}
REDACTED_MARKER = "***REDACTED***"

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/app/data/backup"))
BACKUP_INTERVAL_SECONDS = int(os.environ.get("BACKUP_INTERVAL_SECONDS", "300"))  # 5 min
MANIFEST_FILE = "manifest.json"


def _ensure_dir() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _collection_path(name: str) -> Path:
    return BACKUP_DIR / f"{name}.json"


def _manifest_path() -> Path:
    return BACKUP_DIR / MANIFEST_FILE


async def dump_db(db) -> dict:
    """Exporte toutes les collections métier en JSON. Renvoie les stats."""
    _ensure_dir()
    stats: dict = {"collections": {}, "total_docs": 0}
    for name in BACKUP_COLLECTIONS:
        try:
            cursor = db[name].find({})
            docs = await cursor.to_list(length=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Backup %s : lecture impossible (%s)", name, exc)
            continue

        # Sérialisation déterministe pour des diffs Git lisibles.
        # json_util gère ObjectId, datetime, etc.
        payload = json.loads(json_util.dumps(docs))
        # Tri stable des documents : par 'id' (UUID métier) puis par '_id'.
        def _sort_key(d: dict) -> str:
            return str(d.get("id") or d.get("_id") or "")
        payload_sorted = sorted(payload, key=_sort_key)
        # Redacter les champs sensibles dans la collection settings
        if name == "settings":
            for doc in payload_sorted:
                for field in SENSITIVE_FIELDS:
                    if field in doc and doc[field]:
                        doc[field] = REDACTED_MARKER
        path = _collection_path(name)
        path.write_text(
            json.dumps(payload_sorted, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        stats["collections"][name] = len(payload_sorted)
        stats["total_docs"] += len(payload_sorted)

    manifest = {
        "last_dump_at": datetime.now(timezone.utc).isoformat(),
        "collections": stats["collections"],
        "total_docs": stats["total_docs"],
    }
    _manifest_path().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info("Backup terminé : %d documents", stats["total_docs"])
    return manifest


async def restore_db(db, *, drop_existing: bool = False) -> dict:
    """Restaure les collections depuis les fichiers JSON. Renvoie les stats."""
    _ensure_dir()
    stats: dict = {"collections": {}, "total_docs": 0}
    for name in BACKUP_COLLECTIONS:
        path = _collection_path(name)
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            docs = json_util.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Backup %s : lecture JSON impossible (%s)", name, exc)
            continue
        if not isinstance(docs, list) or not docs:
            continue
        # Pour settings : préserver les secrets actuels en DB s'ils sont redactés dans le backup
        if name == "settings":
            current_secrets: dict = {}
            try:
                current = await db.settings.find_one({"_id": "global"}) or {}
                for f in SENSITIVE_FIELDS:
                    if current.get(f):
                        current_secrets[f] = current[f]
            except Exception:
                pass
            for doc in docs:
                for f in SENSITIVE_FIELDS:
                    if doc.get(f) == REDACTED_MARKER:
                        # On garde la valeur actuelle en DB si elle existe, sinon on supprime
                        if f in current_secrets:
                            doc[f] = current_secrets[f]
                        else:
                            doc.pop(f, None)
        if drop_existing:
            await db[name].delete_many({})
        # Insertion en bulk ; on ignore les doublons (clé _id).
        try:
            await db[name].insert_many(docs, ordered=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Backup %s : insert_many partiel (%s)", name, exc)
        stats["collections"][name] = len(docs)
        stats["total_docs"] += len(docs)
    logger.info("Restauration terminée : %d documents", stats["total_docs"])
    return stats


async def restore_if_empty(db) -> Optional[dict]:
    """Si la collection prospects est vide ET qu'un backup existe, restaure tout."""
    prospects_count = await db.prospects.count_documents({})
    if prospects_count > 0:
        return None
    backup_file = _collection_path("prospects")
    if not backup_file.exists():
        logger.info("Backup auto-restore : aucune sauvegarde trouvée (%s)", backup_file)
        return None
    try:
        raw = backup_file.read_text(encoding="utf-8")
        docs = json_util.loads(raw)
    except Exception:
        return None
    if not docs:
        return None
    logger.warning(
        "Base prospects vide + backup détecté (%d docs) → restauration auto.",
        len(docs),
    )
    return await restore_db(db, drop_existing=True)


async def backup_status(db) -> dict:
    """Renvoie l'état actuel du backup (dernier dump, taille, comptes)."""
    _ensure_dir()
    info: dict = {
        "backup_dir": str(BACKUP_DIR),
        "interval_seconds": BACKUP_INTERVAL_SECONDS,
        "manifest": None,
        "current_db": {},
        "files": [],
    }
    manifest_path = _manifest_path()
    if manifest_path.exists():
        try:
            info["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    for name in BACKUP_COLLECTIONS:
        info["current_db"][name] = await db[name].count_documents({})
        path = _collection_path(name)
        if path.exists():
            info["files"].append({
                "name": name,
                "size_kb": round(path.stat().st_size / 1024, 1),
                "modified_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    return info


async def backup_loop(db) -> None:
    """Boucle de dump périodique. À lancer dans une tâche asyncio."""
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
            await dump_db(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backup loop : erreur (%s)", exc)
