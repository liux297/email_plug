import imaplib
import logging
import ssl
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class MoveEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Move Email] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

        source_folder = tool_parameters.get("source_folder", "INBOX")
        target_folder = tool_parameters.get("target_folder", "").strip()
        email_ids = tool_parameters.get("email_ids", "").strip()

        if not email_ids:
            yield self.create_json_message({
                "status": "error",
                "message": "email_ids is required"
            })
            return

        if not target_folder:
            yield self.create_json_message({
                "status": "error",
                "message": "target_folder is required"
            })
            return

        id_list = [eid.strip() for eid in email_ids.split(",") if eid.strip()]
        logger.info(f"Moving {len(id_list)} email(s) from {source_folder} to {target_folder}")

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

            status, _ = mail.select(source_folder)
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to select source folder: {source_folder}"
                })
                return

            success_count = 0
            failed_ids = []

            for eid in id_list:
                try:
                    status, _ = mail.copy(eid.encode(), target_folder)
                    if status == "OK":
                        mail.store(eid.encode(), '+FLAGS', '(\\Deleted)')
                        success_count += 1
                    else:
                        failed_ids.append(eid)
                except Exception as e:
                    logger.warning(f"Failed to move email {eid}: {e}")
                    failed_ids.append(eid)

            if success_count > 0:
                mail.expunge()

            mail.logout()

            yield self.create_json_message({
                "status": "success" if success_count > 0 else "error",
                "message": f"Moved {success_count} email(s) from {source_folder} to {target_folder}",
                "source_folder": source_folder,
                "target_folder": target_folder,
                "success_count": success_count,
                "failed_ids": failed_ids
            })

        except Exception as e:
            logger.error(f"Move email failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"Failed to move emails: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
