from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail


def _provider() -> str:
    return str(getattr(settings, "OTP_PROVIDER", "smtp")).strip().lower()


def send_password_reset_otp(*, to_email: str, otp_code: str, reset_link: str) -> None:
    subject = "Alemeno Leave Tracker - Password Reset OTP"
    text_body = (
        f"Your OTP is: {otp_code}\n\n"
        f"It expires in 10 minutes.\n\n"
        f"Reset link: {reset_link}\n"
    )

    provider = _provider()
    if provider == "resend":
        _send_with_resend(to_email=to_email, subject=subject, text_body=text_body)
        return

    send_mail(subject, text_body, None, [to_email], fail_silently=False)


def _send_with_resend(*, to_email: str, subject: str, text_body: str) -> None:
    api_key = str(getattr(settings, "RESEND_API_KEY", "")).strip()
    from_email = str(getattr(settings, "OTP_FROM_EMAIL", "")).strip() or str(
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
    ).strip()
    endpoint = str(getattr(settings, "RESEND_API_URL", "https://api.resend.com/emails")).strip()

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is missing")
    if not from_email:
        raise RuntimeError("OTP_FROM_EMAIL/DEFAULT_FROM_EMAIL is missing")

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=int(getattr(settings, "EMAIL_TIMEOUT", 15))) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Resend error status={resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Resend HTTPError status={exc.code} body={detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend URLError: {exc.reason}") from exc
