import base64
import email
import imaplib
import logging
import ssl
from collections.abc import Generator
from email.header import decode_header
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


def decode_header_value(value: str) -> str:
    if not value:
        return ""
    decoded = ""
    try:
        parts = decode_header(value)
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded += part.decode(charset or "utf-8", errors="replace")
            else:
                decoded += part
    except Exception:
        decoded = value
    return decoded


class GetAttachmentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Get Attachment] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

        folder = tool_parameters.get("folder", "INBOX")
        email_id = tool_parameters.get("email_id", "").strip()
        attachment_index = int(tool_parameters.get("attachment_index", 0) or 0)
        max_size_mb = int(tool_parameters.get("max_size_mb", 10) or 10)
        attachment_format = tool_parameters.get("attachment_format", "base64") or "base64"

        if not email_id:
            yield self.create_json_message({
                "status": "error",
                "message": "email_id is required"
            })
            return

        max_size_bytes = max_size_mb * 1024 * 1024
        logger.info(f"Getting attachment from email {email_id} in {folder}, index={attachment_index}, max_size={max_size_mb}MB")

        mail = None
        try:
            if imap_encrypt.upper() == "SSL":
                ctx = ssl.create_default_context()
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ctx, timeout=120)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=120)
                if imap_encrypt.upper() == "TLS":
                    mail.starttls()

            mail.login(email_account, email_password)
            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to select folder: {folder}"
                })
                return

            status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to fetch email {email_id}"
                })
                return

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = decode_header_value(msg.get("Subject", ""))
            attachments = []

            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                if filename or "attachment" in content_disp:
                    filename_decoded = decode_header_value(filename) if filename else "attachment"
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append({
                            "filename": filename_decoded,
                            "content_type": content_type,
                            "size": len(payload),
                            "content": payload
                        })

            mail.logout()

            if not attachments:
                yield self.create_json_message({
                    "status": "error",
                    "message": f"No attachments found in email {email_id}",
                    "email_subject": subject
                })
                return

            if attachment_index == -1:
                attachment_list = []
                for i, att in enumerate(attachments):
                    attachment_list.append({
                        "index": i,
                        "filename": att["filename"],
                        "content_type": att["content_type"],
                        "size": att["size"],
                        "size_human": self._format_size(att["size"])
                    })

                yield self.create_json_message({
                    "status": "success",
                    "email_id": email_id,
                    "email_subject": subject,
                    "total_attachments": len(attachments),
                    "attachments": attachment_list
                })
                return

            if attachment_index >= len(attachments):
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Attachment index {attachment_index} out of range. Email has {len(attachments)} attachment(s).",
                    "email_subject": subject
                })
                return

            att = attachments[attachment_index]

            if att["size"] > max_size_bytes:
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Attachment size ({self._format_size(att['size'])}) exceeds limit ({max_size_mb}MB)",
                    "filename": att["filename"],
                    "size": att["size"]
                })
                return

            result = {
                "status": "success",
                "email_id": email_id,
                "email_subject": subject,
                "attachment_index": attachment_index,
                "total_attachments": len(attachments),
                "filename": att["filename"],
                "content_type": att["content_type"],
                "size": att["size"],
                "size_human": self._format_size(att["size"])
            }

            if attachment_format == "url":
                try:
                    upload_resp = self.session.file.upload(
                        filename=att["filename"],
                        content=att["content"],
                        mimetype=att["content_type"]
                    )
                    result["upload_file_id"] = upload_resp.id
                    result["url"] = upload_resp.preview_url or ""
                    result["format"] = "url"
                    logger.info(f"Uploaded attachment '{att['filename']}' -> {upload_resp.id}")
                except Exception as e:
                    logger.warning(f"Failed to upload attachment '{att['filename']}': {e}, falling back to base64")
                    result["content_base64"] = base64.b64encode(att["content"]).decode('utf-8')
                    result["format"] = "base64"
            else:
                result["content_base64"] = base64.b64encode(att["content"]).decode('utf-8')
                result["format"] = "base64"

            logger.info(f"Returning attachment: {att['filename']} ({self._format_size(att['size'])})")

            yield self.create_json_message(result)

        except Exception as e:
            logger.error(f"Get attachment failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"Failed to get attachment: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
