"""Récupération des réponses prospects depuis la boîte mail (IMAP).

Cas typique : le MX du domaine pointe vers OVH/Gmail/etc. et pas vers SendGrid.
Les vraies réponses arrivent dans la boîte personnelle de l'utilisateur, pas
chez SendGrid. On lit donc directement via IMAP.

Fournisseurs courants :
  - OVH      : ssl0.ovh.net  : 993 (SSL)
  - Gmail    : imap.gmail.com : 993 (SSL, mot de passe d'application requis)
  - Outlook  : outlook.office365.com : 993 (SSL)
  - ProtonMail : nécessite Bridge
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

logger = logging.getLogger(__name__)


# Mots-clés importés de webhook.py pour classifier
STOP_RE = re.compile(r"\b(stop|d[ée]sabonn\w*|ne plus|pas int[ée]ress|plus de mail|spam)\b", re.I)
INTERESSE_RE = re.compile(r"\b(oui|int[ée]ress[ée]?s?|rappeler|rappelez|rendez-vous|rdv|devis)\b", re.I)
AUTOREPLY_SUBJECT_RE = re.compile(
    r"(automatic reply|out of office|absence|hors du bureau|delivery status|undelivered|"
    r"mail delivery|postmaster|mailer-daemon|notification|do not reply|ne pas r[ée]pondre)",
    re.I,
)


def classify(text: str, subject: str = "") -> str:
    full = f"{subject}\n{text}"
    if STOP_RE.search(full):
        return "desabonne"
    if INTERESSE_RE.search(full):
        return "interesse"
    return "repondu"


def _decode_str(s: Optional[str]) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for content, enc in parts:
        if isinstance(content, bytes):
            try:
                out.append(content.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(content.decode("utf-8", errors="replace"))
        else:
            out.append(content)
    return "".join(out).strip()


def _extract_body(msg) -> str:
    """Extrait le texte brut d'un email (multipart ou simple)."""
    candidates_text = []
    candidates_html = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except LookupError:
                decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                candidates_text.append(decoded)
            elif ctype == "text/html":
                candidates_html.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except LookupError:
                decoded = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                candidates_html.append(decoded)
            else:
                candidates_text.append(decoded)

    if candidates_text:
        return "\n".join(candidates_text).strip()
    if candidates_html:
        html = candidates_html[0]
        # Strip HTML basique
        text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n\s*\n", "\n\n", text).strip()
        return text
    return ""


def _strip_quoted(body: str) -> str:
    """Enlève la citation du message original (lignes commençant par > ou bloc 'Le ... a écrit :')."""
    if not body:
        return ""
    lines = body.splitlines()
    out = []
    for line in lines:
        # Coupe à partir du 1er marqueur de citation classique
        if re.match(r"^\s*(>+|Le .+ a écrit\s*:|On .+ wrote:|De\s*:|From\s*:|---+\s*Original)", line):
            break
        out.append(line)
    return "\n".join(out).strip()


def fetch_recent_messages_sync(
    host: str, port: int, user: str, password: str,
    since_days: int = 30, folder: str = "INBOX",
    max_messages: int = 500,
    self_email: str = "",
) -> list[dict]:
    """Lit les emails reçus récents. Synchrone, à appeler via asyncio.to_thread.

    Renvoie une liste de dicts : {from_name, from_email, subject, date, body, body_excerpt, uid}.
    """
    self_lc = (self_email or "").lower()
    self_domain = self_lc.split("@", 1)[1] if "@" in self_lc else ""
    results: list[dict] = []

    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(user, password)
        M.select(folder, readonly=True)
        since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        # SINCE est inclusif. UIDs triés croissants.
        typ, data = M.uid("SEARCH", None, f'(SINCE {since_date})')
        if typ != "OK" or not data or not data[0]:
            return results
        uids = data[0].split()
        # On prend les plus récents en dernier ; on en garde max_messages
        if len(uids) > max_messages:
            uids = uids[-max_messages:]

        for uid in uids:
            try:
                typ, msg_data = M.uid("FETCH", uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                from_name, from_addr = parseaddr(msg.get("From", ""))
                from_addr_lc = (from_addr or "").lower()
                subject = _decode_str(msg.get("Subject", ""))
                date_raw = msg.get("Date", "")
                try:
                    dt = parsedate_to_datetime(date_raw) if date_raw else None
                    date_iso = dt.astimezone(timezone.utc).isoformat() if dt else ""
                except Exception:
                    date_iso = ""

                # Skip mails envoyés par soi-même
                if from_addr_lc == self_lc:
                    continue
                # Skip auto-réponses techniques courantes
                if AUTOREPLY_SUBJECT_RE.search(subject or ""):
                    continue
                # Skip mailer-daemon / postmaster
                if from_addr_lc.startswith(("mailer-daemon", "postmaster")):
                    continue

                body = _extract_body(msg)
                body_clean = _strip_quoted(body)[:4000]
                excerpt = (body_clean[:500] + ("…" if len(body_clean) > 500 else "")).strip()

                results.append({
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "from_name": _decode_str(from_name),
                    "from_email": from_addr_lc,
                    "subject": subject,
                    "date": date_iso,
                    "body": body_clean,
                    "body_excerpt": excerpt,
                    "message_id": msg.get("Message-ID", "").strip(),
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("IMAP fetch uid=%s : %s", uid, exc)
                continue
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return results


async def fetch_recent_messages(*args, **kwargs) -> list[dict]:
    return await asyncio.to_thread(fetch_recent_messages_sync, *args, **kwargs)


def test_connection_sync(host: str, port: int, user: str, password: str) -> dict:
    try:
        M = imaplib.IMAP4_SSL(host, port)
        M.login(user, password)
        typ, data = M.list()
        folders = []
        if typ == "OK" and data:
            for entry in data[:5]:
                if entry:
                    folders.append(entry.decode("utf-8", errors="replace"))
        M.logout()
        return {"ok": True, "folders_sample": folders}
    except imaplib.IMAP4.error as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def test_connection(host: str, port: int, user: str, password: str) -> dict:
    return await asyncio.to_thread(test_connection_sync, host, port, user, password)
