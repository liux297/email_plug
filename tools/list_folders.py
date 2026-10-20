import imaplib
import logging
import re
import ssl
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class ListFoldersTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [List Folders] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

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

            status, folder_list = mail.list()
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": "Failed to list folders"
                })
                return

            folders = []
            for folder_info in folder_list:
                if isinstance(folder_info, bytes):
                    folder_str = folder_info.decode('utf-8', errors='replace')
                    match = re.search(r'"([^"]*)"$|(\S+)$', folder_str)
                    if match:
                        folder_name = match.group(1) or match.group(2)
                        folders.append({
                            "name": folder_name,
                            "raw": folder_str
                        })

            mail.logout()
            logger.info(f"Found {len(folders)} folders")

            yield self.create_json_message({
                "status": "success",
                "total_folders": len(folders),
                "folders": [f["name"] for f in folders]
            })

        except Exception as e:
            logger.error(f"List folders failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"Failed to list folders: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
