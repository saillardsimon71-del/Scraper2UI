"""Import des prospects depuis l'historique d'envoi SendGrid.

Permet de reconstituer la base prospects après une perte de données :
on liste tous les emails envoyés via /v3/messages, on dédoublonne par
destinataire, et on crée un prospect par adresse avec l'historique de l'envoi.
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
PAGE_LIMIT = 1000  # max imposé par SendGrid


# Pattern pour extraire un site depuis le subject ("Votre site https://www.X.fr a du potentiel")
_URL_RE = re.compile(r"https?://(?:www\.)?([A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
# Subjects internes à ignorer (réponses inbound forwardées vers soi-même, tests, etc.)
_SUBJECT_IGNORE = re.compile(
    r"^\s*(\[Réponse prospect\]|TEST |Test |re:\s*test |Bounce |Webhook )",
    re.IGNORECASE,
)


def _build_query(from_email: str, since_iso: str, until_iso: str) -> str:
    """Construit la query SendGrid Activity. Format particulier (DSL).

    Doc : https://docs.sendgrid.com/api-reference/e-mail-activity/filter-all-messages
    """
    parts = [
        f'from_email LIKE "{from_email}"',
        f'last_event_time BETWEEN TIMESTAMP "{since_iso}" AND TIMESTAMP "{until_iso}"',
    ]
    return " AND ".join(parts)


async def fetch_sent_messages(
    api_key: str,
    from_email: str,
    since_days: int = 30,
    max_pages: int = 10,
) -> list[dict]:
    """Récupère tous les messages envoyés depuis `from_email` sur la période.

    SendGrid Activity Feed garde 30 jours d'historique max (illimité avec
    l'add-on Email Activity History). Le trial Pro donne accès sur 7 jours.
    """
    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(days=since_days)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    until_iso = until_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = _build_query(from_email, since_iso, until_iso)

    all_messages: list[dict] = []
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(max_pages):
            url = f"{SENDGRID_API}/messages?limit={PAGE_LIMIT}&query={quote(query)}"
            if page > 0 and all_messages:
                # Pagination par last_event_time : on récupère les antérieurs au dernier message
                last_time = all_messages[-1].get("last_event_time")
                if not last_time:
                    break
                # Adapter la query pour les messages PLUS ANCIENS que last_time
                new_query = (
                    f'from_email LIKE "{from_email}" AND '
                    f'last_event_time BETWEEN TIMESTAMP "{since_iso}" '
                    f'AND TIMESTAMP "{last_time}"'
                )
                url = f"{SENDGRID_API}/messages?limit={PAGE_LIMIT}&query={quote(new_query)}"

            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("SendGrid /messages : HTTP %s — %s",
                               resp.status_code, resp.text[:200])
                break

            data = resp.json()
            messages = data.get("messages", [])
            if not messages:
                break

            # Dédoublonner par msg_id (la pagination peut overlapper)
            existing_ids = {m["msg_id"] for m in all_messages}
            new_msgs = [m for m in messages if m["msg_id"] not in existing_ids]
            all_messages.extend(new_msgs)

            if len(messages) < PAGE_LIMIT:
                break  # dernière page

    return all_messages


def _extract_site_from_subject(subject: str) -> str:
    if not subject:
        return ""
    m = _URL_RE.search(subject)
    if m:
        return m.group(0)
    return ""


def _entreprise_from_email_or_subject(to_email: str, subject: str) -> str:
    """Heuristique pour deviner un nom d'entreprise utilisable."""
    site = _extract_site_from_subject(subject)
    if site:
        # extraire le domaine "racine"
        m = _URL_RE.search(site)
        if m:
            domain = m.group(1).split(".")[0]
            return domain.replace("-", " ").title()
    # fallback : partie domaine de l'email
    if "@" in to_email:
        domain = to_email.split("@", 1)[1]
        root = domain.split(".")[0]
        return root.replace("-", " ").title()
    return ""


def aggregate_by_recipient(
    messages: list[dict],
    self_email: str,
) -> dict[str, dict]:
    """Dédoublonne par to_email, garde le DERNIER envoi (le plus récent).

    Filtre :
      - les emails envoyés à soi-même (forwards d'inbound, tests DKIM…)
      - les subjects identifiés comme internes (TEST, [Réponse prospect]…)
    """
    by_to: dict[str, dict] = {}
    self_email_lc = self_email.lower()
    self_domain = self_email_lc.split("@", 1)[1] if "@" in self_email_lc else ""

    for m in messages:
        to_email = (m.get("to_email") or "").lower().strip()
        subject = m.get("subject") or ""
        if not to_email or "@" not in to_email:
            continue
        # Skip envois à soi / au domaine d'envoi
        if to_email == self_email_lc:
            continue
        if self_domain and to_email.endswith("@" + self_domain):
            continue
        # Skip subjects internes
        if _SUBJECT_IGNORE.match(subject):
            continue

        existing = by_to.get(to_email)
        if existing is None or m.get("last_event_time", "") > existing.get("last_event_time", ""):
            by_to[to_email] = m

    return by_to
