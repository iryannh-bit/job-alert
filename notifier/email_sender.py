"""
Envoi des emails d'alerte et de summary.

Configuration requise (variables d'env) :
  SMTP_EMAIL     : adresse Gmail qui envoie (ex: job.alert.sender@gmail.com)
  SMTP_PASSWORD  : App Password Gmail (16 caractères, pas le mot de passe normal)

Structure des emails :
  - Alerte instantanée : 1 mail par offre
  - Summary bi-journalier : récap de toutes les offres des 48h
  - Cover letter ready : champ `cover_letter` optionnel dans job dict
"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime

logger = logging.getLogger("email_sender")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

LABEL_PPT  = "🎯 Entreprise ciblée"
LABEL_RECH = "🔍 Recherche générale"


class EmailSender:
    def __init__(self):
        self.sender_email    = os.environ["SMTP_EMAIL"]
        self.sender_password = os.environ["SMTP_PASSWORD"]

    # ──────────────────────────────────────────────────────────
    # Alerte instantanée (1 offre)
    # ──────────────────────────────────────────────────────────
    def send_alert(self, to: str, job: dict, alert_type: str):
        label = LABEL_PPT if alert_type == "pour_plus_tard" else LABEL_RECH
        subject = f"[{label}] {job.get('title', 'Nouveau poste')} — {job.get('company', '')}"

        html_body = self._build_alert_html(job, label)
        msg = self._build_message(to=to, subject=subject, html=html_body)

        # ── Pièce jointe lettre de motivation (si présente) ──
        # Activé quand cover_letter_enabled=True dans le futur.
        cover_letter_path = job.get("cover_letter_path")
        if cover_letter_path and os.path.exists(cover_letter_path):
            with open(cover_letter_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(cover_letter_path)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)
            logger.info(f"  Lettre de motivation jointe : {filename}")

        self._send(to, msg)
        logger.info(f"  📧 Alerte envoyée → {to} : {job.get('title')} @ {job.get('company')}")

    # ──────────────────────────────────────────────────────────
    # Summary bi-journalier
    # ──────────────────────────────────────────────────────────
    def send_summary(self, to: str, jobs: list[dict], alert_type: str):
        if not jobs:
            return
        label = LABEL_PPT if alert_type == "pour_plus_tard" else LABEL_RECH
        subject = f"[Summary {label}] {len(jobs)} offre(s) — {datetime.now().strftime('%d/%m/%Y')}"
        html_body = self._build_summary_html(jobs, label)
        msg = self._build_message(to=to, subject=subject, html=html_body)
        self._send(to, msg)
        logger.info(f"  📧 Summary envoyé → {to} ({len(jobs)} offres)")

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────
    def _build_alert_html(self, job: dict, label: str) -> str:
        location = job.get('location', '') or 'Non précisée'
        url = job.get('url', '#') or '#'
        summary = job.get('summary', '') or ''
        description = job.get('description', '') or ''
        desc_text = description[:500] + '…' if len(description) > 500 else description

        summary_block = f"""
    <div style="background:#f0f4ff;border-left:4px solid #1a1a2e;padding:12px 16px;margin:16px 0;border-radius:0 6px 6px 0;">
      <p style="margin:0;color:#1a1a2e;font-size:14px;font-style:italic;">{summary}</p>
    </div>""" if summary else ""

        return f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:640px;margin:auto;">
  <div style="background:#1a1a2e;padding:20px;border-radius:8px 8px 0 0;">
    <h2 style="color:#e0e0ff;margin:0;">💼 Nouvelle offre — {label}</h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
    <h3 style="margin-top:0;color:#1a1a2e;">{job.get('title','N/A')}</h3>
    <p style="margin:4px 0;font-size:15px;">🏢 <strong>{job.get('company','N/A')}</strong></p>
    <p style="margin:4px 0;font-size:14px;color:#555;">📍 {location}</p>
    <p style="margin:4px 0;font-size:14px;color:#555;">📄 {job.get('contract_type','Stage')}</p>
    {summary_block}
    <hr style="margin:16px 0;border:none;border-top:1px solid #eee;">
    <p style="color:#555;line-height:1.6;font-size:14px;">{desc_text}</p>
    <div style="text-align:center;margin-top:24px;">
      <a href="{url}"
         style="background:#1a1a2e;color:#fff;padding:12px 32px;
                text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px;">
        Voir l'offre →
      </a>
    </div>
    <p style="font-size:11px;color:#aaa;margin-top:24px;text-align:center;">
      Alerte automatique Job Alert
    </p>
  </div>
</body></html>"""

    def _build_summary_html(self, jobs: list[dict], label: str) -> str:
        rows = ""
        for j in jobs:
            location = j.get('location', '') or '—'
            url = j.get('url', '#') or '#'
            summary = j.get('summary', '') or ''
            summary_line = f'<br><span style="color:#1a1a2e;font-size:12px;font-style:italic;">{summary}</span>' if summary else ''
            rows += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #eee;vertical-align:top;">
            <strong style="font-size:14px;">{j.get('title','N/A')}</strong><br>
            <span style="color:#555;font-size:13px;">🏢 {j.get('company','')}</span><br>
            <span style="color:#888;font-size:12px;">📍 {location}</span>
            {summary_line}
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #eee;vertical-align:middle;text-align:center;white-space:nowrap;">
            <a href="{url}" style="background:#1a1a2e;color:#fff;padding:8px 16px;
               text-decoration:none;border-radius:4px;font-size:13px;font-weight:bold;">
              Voir →
            </a>
          </td>
        </tr>"""

        return f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:700px;margin:auto;">
  <div style="background:#1a1a2e;padding:20px;border-radius:8px 8px 0 0;">
    <h2 style="color:#e0e0ff;margin:0;">📋 Récap 24h — {label}</h2>
    <p style="color:#aaa;margin:4px 0 0;">{len(jobs)} offre(s) trouvée(s)</p>
  </div>
  <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f5f5f5;">
          <th style="padding:10px 8px;text-align:left;font-size:13px;">Poste</th>
          <th style="padding:10px 8px;text-align:center;font-size:13px;">Lien</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="font-size:11px;color:#aaa;margin-top:24px;text-align:center;">
      Récap quotidien Job Alert • Envoyé tous les jours à 18h
    </p>
  </div>
</body></html>"""

    def _build_message(self, to: str, subject: str, html: str) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["From"]    = self.sender_email
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))
        return msg

    def _send(self, to: str, msg: MIMEMultipart):
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(self.sender_email, self.sender_password)
            smtp.sendmail(self.sender_email, to, msg.as_string())
