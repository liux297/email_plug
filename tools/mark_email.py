import imaplib
import logging
import ssl
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class MarkEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Mark Email] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

        folder = tool_parameters.get("folder", "INBOX")
        email_ids = tool_parameters.get("email_ids", "").strip()
        mark_as = tool_parameters.get("mark_as", "read")

        if not email_ids:
            yield self.create_json_message({
                "status": "error",
                "message": "email_ids is required"
            })
            return

        id_list = [eid.strip() for eid in email_ids.split(",") if eid.strip()]
        logger.info(f"Marking {len(id_list)} email(s) as {mark_as} in {folder}")

        mail = None
        try:
            if imap_encrypt.upper() == "SSL":
                ctx = ssl.create_default_context()
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ctx, timeout=60)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=60)
                if imap_encrypt.upper() == "TLS":
                    mail.starttls()

            mail.login(email_account, email_password)
            status, _ = mail.select(folder)
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to select folder: {folder}"
                })
                return

            if mark_as.lower() == "unread":
                flag_command = '+FLAGS (\\Unseen)'
                flag_name = '\\Unseen'
            else:
                flag_command = '+FLAGS (\\Seen)'
                flag_name = '\\Seen'

            success_count = 0
            failed_ids = []

            for eid in id_list:
                try:
                    if mark_as.lower() == "unread":
                        status, _ = mail.store(eid.encode(), '-FLAGS', '(\\Seen)')
                    else:
                        status, _ = mail.store(eid.encode(), '+FLAGS', '(\\Seen)')

                    if status == "OK":
                        success_count += 1
                    else:
                        failed_ids.append(eid)
                except Exception as e:
                    logger.warning(f"Failed to mark email {eid}: {e}")
                    failed_ids.append(eid)

            mail.logout()

            yield self.create_json_message({
                "status": "success" if success_count > 0 else "error",
                "message": f"Marked {success_count} email(s) as {mark_as}",
                "marked_as": mark_as,
                "folder": folder,
                "success_count": success_count,
                "failed_ids": failed_ids
            })

        except Exception as e:
            logger.error(f"Mark email failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"Failed to mark emails: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
