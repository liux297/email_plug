import base64
import logging
import re
import smtplib
from collections.abc import Generator
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def parse_email_list(emails_str: str) -> list[str]:
    if not emails_str:
        return []
    emails = [e.strip() for e in re.split(r'[,;]', emails_str) if e.strip()]
    return emails


class SendEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Send Email] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        smtp_host = credentials.get("smtp_host", "")
        smtp_port = int(credentials.get("smtp_port", 587))
        smtp_user = credentials.get("email_account", "")
        smtp_password = credentials.get("email_password", "")
        encrypt_method = credentials.get("smtp_encrypt_method", "TLS")

        to_emails = parse_email_list(tool_parameters.get("to_email", ""))
        cc_emails = parse_email_list(tool_parameters.get("cc_email", ""))
        bcc_emails = parse_email_list(tool_parameters.get("bcc_email", ""))
        subject = tool_parameters.get("subject", "").strip()
        body = tool_parameters.get("body", "")
        body_type = tool_parameters.get("body_type", "plain")
        sender_name = tool_parameters.get("sender_name", "").strip()
        attachments = tool_parameters.get("attachments", "")

        logger.info(f"SMTP: {smtp_host}:{smtp_port}, user: {smtp_user}")
        logger.info(f"To: {to_emails}, CC: {cc_emails}, BCC: {bcc_emails}, Subject: {subject}")

        if not to_emails:
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_parameter",
                "message": "At least one recipient email is required."
            })
            return

        if not subject:
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_parameter",
                "message": "Subject is required."
            })
            return

        invalid_emails = []
        for email in to_emails + cc_emails + bcc_emails:
            if not validate_email(email):
                invalid_emails.append(email)

        if invalid_emails:
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_address",
                "message": f"Invalid email addresses: {', '.join(invalid_emails)}"
            })
            return

        try:
            has_attachments = bool(attachments and attachments.strip())

            if has_attachments or body_type == "html":
                msg = MIMEMultipart()
                msg.attach(MIMEText(body, body_type, "utf-8"))
            else:
                msg = MIMEText(body, "plain", "utf-8")

            if sender_name:
                msg["From"] = formataddr((sender_name, smtp_user))
            else:
                msg["From"] = smtp_user

            msg["To"] = ", ".join(to_emails)
            if cc_emails:
                msg["Cc"] = ", ".join(cc_emails)
            msg["Subject"] = subject

            if has_attachments:
                attachment_list = self._parse_attachments(attachments)
                for filename, content in attachment_list:
                    part = MIMEApplication(content)
                    part.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(part)
                logger.info(f"Attached {len(attachment_list)} file(s)")

            all_recipients = to_emails + cc_emails + bcc_emails

            logger.info(f"Connecting to SMTP server ({encrypt_method})...")
            if encrypt_method.upper() == "SSL":
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=60)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=60)
                if encrypt_method.upper() == "TLS":
                    server.starttls()

            logger.info("Logging in...")
            server.login(smtp_user, smtp_password)
            logger.info(f"Sending email to {len(all_recipients)} recipient(s)...")
            server.sendmail(smtp_user, all_recipients, msg.as_string())
            server.quit()
            logger.info("Email sent successfully")

            yield self.create_json_message({
                "status": "success",
                "message": "Email sent successfully",
                "from": smtp_user,
                "to": to_emails,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "subject": subject,
                "attachments_count": len(self._parse_attachments(attachments)) if has_attachments else 0,
                "timestamp": datetime.now().isoformat(timespec="seconds")
            })

        except smtplib.SMTPConnectError as e:
            logger.error(f"SMTP connection failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "connection_timeout",
                "message": f"Failed to connect to SMTP server: {e}"
            })
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "auth_failed",
                "message": f"SMTP authentication failed: {e}"
            })
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"Recipient refused: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_address",
                "message": f"Recipient refused: {e}"
            })
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "unknown",
                "message": str(e)
            })

    def _parse_attachments(self, attachments_str: str) -> list[tuple[str, bytes]]:
        """Parse attachments from JSON array format: [{"filename": "x.txt", "content_base64": "..."}]"""
        if not attachments_str or not attachments_str.strip():
            return []

        import json
        try:
            attachments = json.loads(attachments_str)
            if not isinstance(attachments, list):
                return []

            result = []
            for att in attachments:
                if isinstance(att, dict):
                    filename = att.get("filename", "attachment")
                    content_b64 = att.get("content_base64", "")
                    if content_b64:
                        content = base64.b64decode(content_b64)
                        result.append((filename, content))
            return result
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse attachments: {e}")
            return []
