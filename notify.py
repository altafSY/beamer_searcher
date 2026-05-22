"""Notification channels. Currently SMS via vtext.com email gateway; Telegram stub for later."""

import os
import smtplib
import logging
from email.message import EmailMessage

import requests

log = logging.getLogger(__name__)

SMS_TO = os.environ.get("SMS_TO", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def _shorten_url(url: str) -> str:
    """Shorten via TinyURL (no auth, no key) so the link survives the SMS
    segment split. Falls back to the original URL on any failure."""
    if not url:
        return ""
    try:
        r = requests.get(
            "https://tinyurl.com/api-create.php",
            params={"url": url},
            timeout=10,
        )
        r.raise_for_status()
        short = r.text.strip()
        if short.startswith("http"):
            return short
        log.warning("tinyurl returned non-URL: %r", short[:120])
    except Exception as e:
        log.warning("URL shorten failed for %s: %s", url, e)
    return url


def _format_sms(match: dict) -> str:
    """Compact SMS body. Aim for a single ~160-char SMS segment so the URL
    isn't split across parts."""
    m = match
    hk = "Y" if m.get("has_harman") else "N"
    # Strip noise so packages fit
    pkgs_raw = m.get("packages") or []
    pkgs_short = [
        p.replace(" Package", "").replace("Connected Package Pro", "ConnectedPro")
        for p in pkgs_raw
    ]
    pkg_str = ", ".join(pkgs_short) if pkgs_short else "none"
    dealer = m["dealer"].replace("BMW of ", "")
    color = (m.get("color") or "").replace(" Metallic", "")
    short_url = _shorten_url(m["url"])
    return (
        f"i4 {m['trim']} @ {dealer}\n"
        f"${m['price']:,} | {m['mileage']:,}mi | {color}\n"
        f"H/K:{hk} | {pkg_str}\n"
        f"{short_url}"
    )


def send_sms(match: dict) -> bool:
    """Send a single match notification as SMS via Gmail->carrier email gateway."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not SMS_TO:
        log.error("GMAIL_USER / GMAIL_APP_PASSWORD / SMS_TO not set; cannot send SMS.")
        return False

    body = _format_sms(match)
    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = SMS_TO
    msg["Subject"] = "BMW i4 match"
    msg.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            s.send_message(msg)
        log.info("SMS sent for VIN %s to %s", match["vin"], SMS_TO)
        return True
    except Exception as e:
        log.error("SMS send failed for VIN %s: %s", match["vin"], e)
        return False


def send_telegram(match: dict) -> bool:
    """Stub for future Telegram bot delivery. Wire up when TELEGRAM_BOT_TOKEN+CHAT_ID are set."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        return False
    # Intentionally not implemented yet.
    log.info("Telegram credentials present but delivery not yet implemented.")
    return False


def notify(match: dict) -> None:
    """Fan out a match to all enabled channels."""
    send_sms(match)
    send_telegram(match)
