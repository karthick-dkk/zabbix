"""
Email Sender
Sends HTML reports (with optional CSV attachments) via SMTP.

Supports:
  - Plain SMTP (port 25)
  - SMTP over TLS/SSL (port 465)
  - SMTP with STARTTLS (port 587)
  - Optional SMTP authentication
  - Multiple recipients
  - Multiple CSV file attachments
"""

import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Union


class MailerError(Exception):
    """Raised when email sending fails."""


class Mailer:
    """
    SMTP mailer that sends Zabbix HTML reports.

    Usage::

        mailer = Mailer(
            host="smtp.example.com",
            port=587,
            use_tls=True,
            username="user@example.com",
            password="secret",
            from_addr="zabbix@example.com",
        )
        mailer.send(
            to=["ops@example.com", "mgr@example.com"],
            subject="Hourly Zabbix Report",
            html_body=html_string,
            attachments={"hourly_events.csv": csv_bytes},
        )
    """

    def __init__(
        self,
        host: str,
        port: int = 25,
        use_tls: bool = False,
        use_starttls: bool = False,
        username: str = None,
        password: str = None,
        from_addr: str = "zabbix-reporter@localhost",
        timeout: int = 30,
        verify_ssl: bool = True,
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls          # SSL/TLS from the start (port 465)
        self.use_starttls = use_starttls  # STARTTLS upgrade (port 587)
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    # ------------------------------------------------------------------
    # Build message
    # ------------------------------------------------------------------

    @staticmethod
    def _build_message(
        from_addr: str,
        to: List[str],
        subject: str,
        html_body: str,
        attachments: Optional[Dict[str, bytes]] = None,
    ) -> MIMEMultipart:
        """Build a MIME multipart email message."""
        msg = MIMEMultipart("mixed")
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(to)
        msg["Subject"] = subject

        # HTML body (with plaintext fallback)
        alt = MIMEMultipart("alternative")
        plain = MIMEText(
            "This email requires an HTML-capable mail client to view.",
            "plain",
            "utf-8",
        )
        html = MIMEText(html_body, "html", "utf-8")
        alt.attach(plain)
        alt.attach(html)
        msg.attach(alt)

        # CSV attachments
        if attachments:
            for filename, content in attachments.items():
                part = MIMEBase("text", "csv")
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=filename,
                )
                part.add_header("Content-Type", "text/csv; charset=utf-8")
                msg.attach(part)

        return msg

    # ------------------------------------------------------------------
    # SSL context
    # ------------------------------------------------------------------

    def _ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html_body: str,
        attachments: Optional[Dict[str, bytes]] = None,
        cc: Optional[List[str]] = None,
    ) -> bool:
        """
        Send an HTML email report.

        Parameters
        ----------
        to          : recipient address or list of addresses
        subject     : email subject line
        html_body   : full HTML string (the rendered report)
        attachments : optional dict of {filename: bytes} for CSV files
        cc          : optional list of CC recipients

        Returns
        -------
        True on success, raises MailerError on failure.
        """
        if isinstance(to, str):
            to = [addr.strip() for addr in to.split(",")]

        all_recipients = list(to)
        if cc:
            all_recipients.extend(cc)

        msg = self._build_message(
            self.from_addr, to, subject, html_body, attachments
        )
        if cc:
            msg["Cc"] = ", ".join(cc)

        try:
            if self.use_tls:
                smtp = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    timeout=self.timeout,
                    context=self._ssl_context(),
                )
            else:
                smtp = smtplib.SMTP(
                    self.host,
                    self.port,
                    timeout=self.timeout,
                )

            with smtp:
                if self.use_starttls and not self.use_tls:
                    smtp.ehlo()
                    smtp.starttls(context=self._ssl_context())
                    smtp.ehlo()

                if self.username and self.password:
                    smtp.login(self.username, self.password)

                smtp.sendmail(
                    self.from_addr,
                    all_recipients,
                    msg.as_bytes(),
                )

        except smtplib.SMTPAuthenticationError as exc:
            raise MailerError(f"SMTP authentication failed: {exc}") from exc
        except smtplib.SMTPException as exc:
            raise MailerError(f"SMTP error: {exc}") from exc
        except OSError as exc:
            raise MailerError(f"Network error: {exc}") from exc

        return True

    # ------------------------------------------------------------------
    # Convenience: send a rendered report dict directly
    # ------------------------------------------------------------------

    def send_report(
        self,
        report_data: Dict,
        html_body: str,
        csv_files: Optional[Dict[str, bytes]] = None,
        to: Union[str, List[str]] = None,
        subject_prefix: str = "[Zabbix]",
    ) -> bool:
        """
        Send a rendered report.

        Parameters
        ----------
        report_data    : the data dict from DataCollector (used for subject)
        html_body      : rendered HTML string from ReportRenderer
        csv_files      : dict of {filename: bytes} from ReportRenderer.render_csv()
        to             : recipient(s) — overrides instance default if set
        subject_prefix : prefix for the email subject line
        """
        title   = report_data.get("title", "Zabbix Report")
        period  = report_data.get("period_label", "")
        ts      = report_data.get("generated_at", "")
        subject = f"{subject_prefix} {title} — {period} [{ts}]"

        recipients = to
        if not recipients:
            raise MailerError("No recipients specified.")

        return self.send(
            to=recipients,
            subject=subject,
            html_body=html_body,
            attachments=csv_files,
        )
