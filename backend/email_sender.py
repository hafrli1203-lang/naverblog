"""Gmail SMTP 이메일 발송 모듈.

환경변수:
  SMTP_EMAIL    — 발신 Gmail 주소
  SMTP_PASSWORD — Gmail 앱 비밀번호 (16자, Google 2FA 필요)

미설정 시 warning 로그만 출력하고 에러 없이 무시.
"""
from __future__ import annotations

import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("naverblog.email")

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

if not SMTP_EMAIL or not SMTP_PASSWORD:
    logger.warning("SMTP_EMAIL / SMTP_PASSWORD 미설정 — 이메일 발송이 비활성화됩니다.")


def _send_smtp(to: str, subject: str, body_html: str) -> None:
    """동기 SMTP 전송 (내부용). 실패 시 로그만 남김."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.warning("SMTP 미설정 — 이메일 미발송: to=%s, subject=%s", to, subject)
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_EMAIL
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to, msg.as_string())
        logger.info("이메일 발송 성공: to=%s, subject=%s", to, subject)
    except Exception as e:
        logger.error("이메일 발송 실패: to=%s, error=%s", to, e)


def send_email_async(to: str, subject: str, body_html: str) -> None:
    """백그라운드 스레드에서 이메일 발송 (API 응답 차단 없음)."""
    t = threading.Thread(target=_send_smtp, args=(to, subject, body_html), daemon=True)
    t.start()


def send_notification_email(
    to_email: str,
    recipient_name: str,
    title: str,
    message: str,
    link: str = "",
) -> None:
    """알림 이메일 HTML 포맷팅 후 비동기 발송."""
    if not to_email:
        return
    link_html = ""
    if link:
        full_link = link if link.startswith("http") else f"https://xn--6j1b00mxunnyck8p.com{link}"
        link_html = f'<p><a href="{full_link}" style="color:#1B9C00;font-weight:600;">바로 확인하기 &rarr;</a></p>'

    body_html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:Pretendard,-apple-system,sans-serif;color:#1a1d1a;">
      <div style="background:#1B9C00;padding:20px 24px;border-radius:12px 12px 0 0;">
        <h2 style="color:#fff;margin:0;font-size:18px;">체험단모집.com</h2>
      </div>
      <div style="background:#fff;padding:24px;border:1px solid #e2e6e1;border-top:none;border-radius:0 0 12px 12px;">
        <p style="margin:0 0 8px;font-size:15px;">안녕하세요, <strong>{recipient_name}</strong>님</p>
        <h3 style="margin:16px 0 8px;font-size:16px;">{title}</h3>
        <p style="color:#525a52;font-size:14px;line-height:1.6;">{message}</p>
        {link_html}
        <hr style="border:none;border-top:1px solid #e2e6e1;margin:20px 0;">
        <p style="font-size:12px;color:#97a097;">이 메일은 체험단모집.com에서 자동 발송되었습니다.</p>
      </div>
    </div>
    """
    send_email_async(to_email, f"[체험단모집] {title}", body_html)
