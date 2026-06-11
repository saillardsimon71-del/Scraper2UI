"""Récupération rétroactive des réponses prospects via SendGrid Activity.

Stratégie : le webhook /sendgrid/inbound ré-envoie chaque réponse prospect
à l'utilisateur sous la forme "[Réponse prospect] Re: <subject original>".
Ces notifications sont visibles dans /v3/messages (filter to_email=self).

On les croise avec les envois sortants (par subject normalisé) pour
retrouver l'email du prospect répondant, puis on marque les prospects.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SENDGRID_API = "https://api.sendgrid.com/v3"
PAGE_LIMIT = 1000

# Préfixe ajouté par webhook.py au subject de la notification
NOTIF_PREFIX_RE = re.compile(
    r"^\s*\[R[ée]ponse prospect\]\s*(?:Re\s*:\s*)?",
    re.IGNORECASE,
)


def _normalize_subject(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"^(?:re\s*:\s*|fw\s*:\s*|fwd\s*:\s*)+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


async def fetch_messages_by_query(
    api_key: str,
    query: str,
    max_pages: int = 5,
) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    all_messages: list[dict] = []
    current_query = query
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(max_pages):
            url = f"{SENDGRID_API}/messages?limit={PAGE_LIMIT}&query={quote(current_query)}"
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("SendGrid query HTTP %s : %s", resp.status_code, resp.text[:200])
                break
            data = resp.json()
            msgs = data.get("messages", [])
            if not msgs:
                break
            existing_ids = {m["msg_id"] for m in all_messages}
            new = [m for m in msgs if m["msg_id"] not in existing_ids]
            all_messages.extend(new)
            if len(msgs) < PAGE_LIMIT:
                break
            # Pagination par last_event_time
            last_time = new[-1].get("last_event_time") if new else None
            if not last_time:
                break
            # Ajoute une borne supérieure
            current_query = f"{query} AND last_event_time < TIMESTAMP \"{last_time}\""
    return all_messages


async def fetch_notifications(api_key: str, self_email: str, since_days: int = 30) -> list[dict]:
    """Récupère les notifications '[Réponse prospect] ...' (envoyées à soi-même)."""
    until_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    since_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        f'from_email LIKE "{self_email}" AND '
        f'to_email LIKE "{self_email}" AND '
        f'last_event_time BETWEEN TIMESTAMP "{since_iso}" AND TIMESTAMP "{until_iso}"'
    )
    all_msgs = await fetch_messages_by_query(api_key, query)
    # Filtre subject "[Réponse prospect]"
    return [m for m in all_msgs if NOTIF_PREFIX_RE.match(m.get("subject", ""))]


async def fetch_outgoing(api_key: str, self_email: str, since_days: int = 30) -> list[dict]:
    """Récupère tous les envois sortants réels (au prospect, pas à soi-même)."""
    until_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    since_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        f'from_email LIKE "{self_email}" AND '
        f'last_event_time BETWEEN TIMESTAMP "{since_iso}" AND TIMESTAMP "{until_iso}"'
    )
    all_msgs = await fetch_messages_by_query(api_key, query)
    self_lc = self_email.lower()
    self_domain = self_lc.split("@", 1)[1] if "@" in self_lc else ""
    # Exclure les envois à soi-même
    return [
        m for m in all_msgs
        if (m.get("to_email", "").lower() != self_lc)
        and not (self_domain and m.get("to_email", "").lower().endswith("@" + self_domain))
    ]


def match_notifications_to_outgoing(
    notifications: list[dict],
    outgoing: list[dict],
) -> list[dict]:
    """Pour chaque notif, retrouve l'envoi sortant correspondant via subject normalisé.

    Retourne une liste enrichie : {notification, original_subject, prospect_email, sent_at, reply_at}
    """
    # Index des envois sortants par subject normalisé (le plus récent prime)
    out_by_subject: dict[str, dict] = {}
    for m in outgoing:
        norm = _normalize_subject(m.get("subject", ""))
        if not norm:
            continue
        existing = out_by_subject.get(norm)
        if existing is None or m.get("last_event_time", "") > existing.get("last_event_time", ""):
            out_by_subject[norm] = m

    results = []
    for notif in notifications:
        raw_subj = notif.get("subject", "")
        # Enlever le préfixe "[Réponse prospect] Re: "
        original_subj = NOTIF_PREFIX_RE.sub("", raw_subj).strip()
        norm = _normalize_subject(original_subj)
        out = out_by_subject.get(norm)
        results.append({
            "notif_msg_id": notif.get("msg_id"),
            "reply_at": notif.get("last_event_time"),
            "original_subject": original_subj,
            "prospect_email": out.get("to_email") if out else None,
            "sent_at": out.get("last_event_time") if out else None,
            "matched": bool(out),
        })
    return results
