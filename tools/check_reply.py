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


class CheckReplyTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Check Reply] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

        folder = tool_parameters.get("folder", "INBOX")
        email_id = tool_parameters.get("email_id", "").strip()
        check_sent_folder = tool_parameters.get("check_sent_folder", True)
        sent_folder = tool_parameters.get("sent_folder", "Sent") or "Sent"
        max_results = int(tool_parameters.get("max_results", 10) or 10)

        if not email_id:
            yield self.create_json_message({
                "status": "error",
                "message": "email_id is required"
            })
            return

        logger.info(f"Checking replies for email {email_id} in {folder}")

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
            
            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to select folder: {folder}"
                })
                return

            status, msg_data = mail.fetch(email_id.encode(), "(RFC822.HEADER)")
            if status != "OK":
                yield self.create_json_message({
                    "status": "error",
                    "message": f"Failed to fetch email {email_id}"
                })
                return

            header_data = msg_data[0][1]
            msg = email.message_from_bytes(header_data)
            
            original_message_id = msg.get("Message-ID", "").strip()
            original_subject = decode_header_value(msg.get("Subject", ""))
            original_from = decode_header_value(msg.get("From", ""))
            original_date = msg.get("Date", "")

            logger.info(f"Original email Message-ID: {original_message_id}")
            logger.info(f"Original subject: {original_subject}")

            if not original_message_id:
                yield self.create_json_message({
                    "status": "warning",
                    "message": "Original email has no Message-ID header, cannot check for replies",
                    "email_id": email_id,
                    "subject": original_subject,
                    "has_replies": False,
                    "replies": []
                })
                return

            replies = []
            
            status, all_messages = mail.search(None, 'ALL')
            all_ids = all_messages[0].split() if all_messages[0] else []
            logger.info(f"Scanning {len(all_ids)} emails in {folder} for replies")

            scan_limit = min(len(all_ids), 1000)
            scan_ids = all_ids[-scan_limit:]

            for eid in reversed(scan_ids):
                if len(replies) >= max_results:
                    break

                if eid.decode() == email_id:
                    continue

                status, msg_data = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES SUBJECT FROM DATE)])")
                if status != "OK":
                    continue

                header_data = msg_data[0][1]
                reply_msg = email.message_from_bytes(header_data)
                
                in_reply_to = reply_msg.get("In-Reply-To", "").strip()
                references = reply_msg.get("References", "").strip()
                
                is_reply = False
                if in_reply_to and original_message_id in in_reply_to:
                    is_reply = True
                elif references and original_message_id in references:
                    is_reply = True

                if is_reply:
                    reply_subject = decode_header_value(reply_msg.get("Subject", ""))
                    reply_from = decode_header_value(reply_msg.get("From", ""))
                    reply_date = reply_msg.get("Date", "")
                    
                    replies.append({
                        "id": eid.decode(),
                        "from": reply_from,
                        "subject": reply_subject,
                        "date": reply_date,
                        "folder": folder
                    })
                    logger.info(f"  Found reply: {reply_subject} from {reply_from}")

            if check_sent_folder and sent_folder != folder:
                try:
                    status, _ = mail.select(sent_folder, readonly=True)
                    if status == "OK":
                        status, sent_messages = mail.search(None, 'ALL')
                        sent_ids = sent_messages[0].split() if sent_messages[0] else []
                        logger.info(f"Scanning {len(sent_ids)} emails in {sent_folder} for sent replies")

                        scan_limit = min(len(sent_ids), 500)
                        scan_ids = sent_ids[-scan_limit:]

                        for eid in reversed(scan_ids):
                            if len(replies) >= max_results:
                                break

                            status, msg_data = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES SUBJECT FROM DATE)])")
                            if status != "OK":
                                continue

                            header_data = msg_data[0][1]
                            reply_msg = email.message_from_bytes(header_data)
                            
                            in_reply_to = reply_msg.get("In-Reply-To", "").strip()
                            references = reply_msg.get("References", "").strip()
                            
                            is_reply = False
                            if in_reply_to and original_message_id in in_reply_to:
                                is_reply = True
                            elif references and original_message_id in references:
                                is_reply = True

                            if is_reply:
                                reply_subject = decode_header_value(reply_msg.get("Subject", ""))
                                reply_from = decode_header_value(reply_msg.get("From", ""))
                                reply_date = reply_msg.get("Date", "")
                                
                                replies.append({
                                    "id": eid.decode(),
                                    "from": reply_from,
                                    "subject": reply_subject,
                                    "date": reply_date,
                                    "folder": sent_folder
                                })
                                logger.info(f"  Found sent reply: {reply_subject}")
                except Exception as e:
                    logger.warning(f"Failed to check sent folder {sent_folder}: {e}")

            mail.logout()

            logger.info(f"Found {len(replies)} replies")

            yield self.create_json_message({
                "status": "success",
                "email_id": email_id,
                "message_id": original_message_id,
                "original_subject": original_subject,
                "original_from": original_from,
                "original_date": original_date,
                "has_replies": len(replies) > 0,
                "reply_count": len(replies),
                "replies": replies
            })

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"IMAP error: {str(e)}"
            })
        except Exception as e:
            logger.error(f"Check reply failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "message": f"Failed to check repliesplies: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
