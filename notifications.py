# backend/notifications.py
import os, base64, smtplib, ssl, logging
from email.message import EmailMessage
from typing import Optional, Dict, Any
try:
    import httpx  # optional, for RESEND provider
except Exception:
    httpx = None

log = logging.getLogger("backend.mail")

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)

def _sender() -> str:
    name = _env("MAIL_DISPLAY_NAME", "KI‑Sicherheit")
    addr = _env("MAIL_FROM", "kontakt@ki-sicherheit.jetzt")
    return f"{name} <{addr}>"

def _admin_to() -> str:
    return _env("ADMIN_EMAIL", "bewertung@ki-sicherheit.jetzt")

def _feedback_url() -> str:
    return _env("FEEDBACK_URL", "https://make.ki-sicherheit.jetzt/feedback/feedback.html")

def _subject(meta: Dict[str, Any], user_email: Optional[str]) -> str:
    branche = meta.get("branche") or meta.get("industry") or "—"
    standort = meta.get("standort") or meta.get("location") or "—"
    who = user_email or meta.get("contact_email") or "Nutzer"
    return f"KI‑Status Report – {branche} · {standort} – {who}"

def _html_admin(meta: Dict[str, Any], user_email: Optional[str]) -> str:
    feedback = _feedback_url()
    t = meta.get("title") or "KI‑Statusbericht"
    date = meta.get("date") or ""
    return f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;">
      <h2 style="margin:0 0 8px">{t}</h2>
      <p style="margin:0 0 12px;color:#333">Neuer Report wurde erstellt am {date}.</p>
      <p style="margin:0 0 12px">Absender (Reply‑To): <b>{user_email or '—'}</b></p>
      <p style="margin:0 0 12px">Feedback: <a href="{feedback}">{feedback}</a></p>
    </div>
    """

def _html_user(meta: Dict[str, Any]) -> str:
    feedback = _feedback_url()
    t = meta.get("title") or "Ihr KI‑Statusbericht"
    return f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;">
      <h2 style="margin:0 0 8px">{t}</h2>
      <p style="margin:0 0 12px;color:#333">Ihr persönlicher Report ist fertig. 
      Diese Mail enthält die PDF im Anhang.</p>
      <p style="margin:0 0 12px">Feedback willkommen: <a href="{feedback}">{feedback}</a></p>
      <p style="margin:16px 0 0;color:#666">Hinweis: Antworten Sie einfach auf diese Mail, 
      wenn Rückfragen bestehen.</p>
    </div>
    """

def _attach_pdf(msg: EmailMessage, pdf_bytes: bytes, filename: str = "KI-Status-Report.pdf"):
    msg.add_attachment(pdf_bytes,
                      maintype="application",
                      subtype="pdf",
                      filename=filename)

def _send_via_smtp(to_email: str, subject: str, html: str,
                   reply_to: Optional[str], pdf_bytes: Optional[bytes]) -> None:
    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "587"))
    user = _env("SMTP_USER")
    pwd  = _env("SMTP_PASS")
    use_ssl = _env("SMTP_SSL", "false").lower() in ("1", "true", "yes")
    if not host or not user or not pwd:
        raise RuntimeError("SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS).")

    msg = EmailMessage()
    msg["From"] = _sender()
    msg["To"] = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content("HTML only.", subtype="plain")
    msg.add_alternative(html, subtype="html")
    if pdf_bytes:
        _attach_pdf(msg, pdf_bytes)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)

def _send_via_resend(to_email: str, subject: str, html: str,
                     reply_to: Optional[str], pdf_bytes: Optional[bytes]) -> None:
    api = _env("RESEND_API_KEY")
    if not api or not httpx:
        raise RuntimeError("RESEND not configured.")
    attachments = []
    if pdf_bytes:
        attachments.append({
            "filename": "KI-Status-Report.pdf",
            "content": base64.b64encode(pdf_bytes).decode("utf-8"),
        })
    payload = {
        "from": _sender(),
        "to": [to_email],
        "subject": subject,
        "html": html,
        "attachments": attachments
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    with httpx.Client(timeout=30) as client:
        r = client.post("https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {api}"},
                        json=payload)
        r.raise_for_status()

def _send(to_email: str, subject: str, html: str,
          reply_to: Optional[str], pdf_bytes: Optional[bytes]) -> None:
    provider = (_env("MAIL_PROVIDER") or "").lower()
    # Try explicit provider, else auto‑fallback: RESEND -> SMTP
    try:
        if provider == "resend":
            _send_via_resend(to_email, subject, html, reply_to, pdf_bytes)
        elif provider == "smtp":
            _send_via_smtp(to_email, subject, html, reply_to, pdf_bytes)
        else:
            # auto
            if _env("RESEND_API_KEY") and httpx:
                _send_via_resend(to_email, subject, html, reply_to, pdf_bytes)
            else:
                _send_via_smtp(to_email, subject, html, reply_to, pdf_bytes)
    except Exception as e:
        log.error("send mail failed: to=%s provider=%s err=%s", to_email, provider or "auto", e)
        raise

def send_admin(pdf_bytes: bytes, meta: Dict[str, Any], user_email: Optional[str]) -> None:
    subj = _subject(meta, user_email)
    html = _html_admin(meta, user_email)
    to = _admin_to()
    _send(to, subj, html, reply_to=user_email, pdf_bytes=pdf_bytes)
    log.info("[mail] admin sent -> %s subj=%s", to, subj)

def send_user(pdf_bytes: bytes, meta: Dict[str, Any], user_email: str) -> None:
    subj = meta.get("title") or "Ihr KI‑Status Report"
    html = _html_user(meta)
    _send(user_email, subj, html, reply_to=_env("MAIL_FROM"), pdf_bytes=pdf_bytes)
    log.info("[mail] user sent -> %s subj=%s", user_email, subj)

def send_both(pdf_bytes: bytes, meta: Dict[str, Any], user_email: Optional[str]) -> None:
    # Admin immer, User wenn vorhanden
    send_admin(pdf_bytes, meta, user_email)
    if user_email:
        send_user(pdf_bytes, meta, user_email)
