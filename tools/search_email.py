import base64
import email
import imaplib
import logging
import re
import ssl
from collections.abc import Generator
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


def html_to_plain_text(html: str) -> str:
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<(br|/p|/div|/li|/tr|/h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


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


def is_ascii_only(text: str) -> bool:
    try:
        text.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


class SearchEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Search Email] Tool invoked ==========")

        credentials = self.runtime.credentials or {}
        imap_host = credentials.get("imap_host", "")
        imap_port = int(credentials.get("imap_port", 993))
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")

        folder = tool_parameters.get("folder", "INBOX")
        sender = tool_parameters.get("sender", "").strip()
        subject = tool_parameters.get("subject", "").strip()
        body_keyword = tool_parameters.get("body_keyword", "").strip()
        start_date = tool_parameters.get("start_date", "").strip()
        end_date = tool_parameters.get("end_date", "").strip()
        days = int(tool_parameters.get("days", 0) or 0)
        unread_only = tool_parameters.get("unread_only", False)
        max_results = int(tool_parameters.get("max_results", 10) or 10)
        include_body = tool_parameters.get("include_body", True)
        include_attachments = tool_parameters.get("include_attachments", False)
        attachment_format = tool_parameters.get("attachment_format", "url") or "url"
        has_reply_filter = tool_parameters.get("has_reply", False)

        logger.info(f"IMAP: {imap_host}:{imap_port} ({imap_encrypt})")
        logger.info(f"Folder: {folder}, Sender: '{sender}', Subject: '{subject}'")
        logger.info(f"Body keyword: '{body_keyword}', Date range: {start_date} to {end_date}, Days: {days}")
        logger.info(f"Unread only: {unread_only}, Max results: {max_results}, Has reply filter: {has_reply_filter}")

        mail = None
        try:
            logger.info("Connecting to IMAP server...")
            if imap_encrypt.upper() == "SSL":
                ctx = ssl.create_default_context()
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ctx, timeout=60)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=60)
                if imap_encrypt.upper() == "TLS":
                    mail.starttls()

            mail.login(email_account, email_password)
            logger.info("Logged in, selecting folder...")
            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                yield self.create_json_message({
                    "error": f"Failed to select folder: {folder}",
                    "total_found": 0,
                    "emails": []
                })
                return

            criteria = []
            subject_needs_client_filter = False
            body_needs_client_filter = bool(body_keyword)

            if sender:
                if is_ascii_only(sender):
                    criteria.append(f'FROM "{sender}"')
                else:
                    criteria.append(f'FROM "{sender}"')

            if subject:
                if is_ascii_only(subject):
                    criteria.append(f'SUBJECT "{subject}"')
                else:
                    subject_needs_client_filter = True
                    logger.info(f"Subject contains non-ASCII, will filter client-side: '{subject}'")

            if unread_only:
                criteria.append('UNSEEN')

            if has_reply_filter:
                criteria.append('ANSWERED')
                logger.info("Reply filter: only answered emails")

            start_dt = parse_date(start_date)
            end_dt = parse_date(end_date)

            if days > 0 and not start_dt:
                start_dt = datetime.now() - timedelta(days=days)

            if start_dt:
                since_str = start_dt.strftime("%d-%b-%Y")
                criteria.append(f'SINCE {since_str}')
                logger.info(f"Date filter: since {since_str}")

            if end_dt:
                before_str = (end_dt + timedelta(days=1)).strftime("%d-%b-%Y")
                criteria.append(f'BEFORE {before_str}')
                logger.info(f"Date filter: before {before_str}")

            use_imap_search = bool(criteria)

            if use_imap_search:
                search_query = " ".join(criteria)
                logger.info(f"IMAP search query: {search_query}")

                status, messages = mail.search(None, search_query)
                email_ids = messages[0].split() if messages[0] else []
                logger.info(f"IMAP server returned {len(email_ids)} results")

                if subject_needs_client_filter or body_needs_client_filter or len(email_ids) < max_results:
                    logger.info("Applying client-side filtering...")
                    if email_ids:
                        candidates = email_ids
                    else:
                        status, all_messages = mail.search(None, 'ALL')
                        candidates = all_messages[0].split() if all_messages[0] else []

                    scan_limit = min(len(candidates), max(max_results * 100, 1000))
                    candidates = candidates[-scan_limit:]
                    logger.info(f"Scanning {len(candidates)} emails locally")

                    matched_ids = []
                    for eid in reversed(candidates):
                        if len(matched_ids) >= max_results:
                            break

                        fetch_fields = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
                        if body_needs_client_filter:
                            fetch_fields = "(BODY.PEEK[])"

                        status, msg_data = mail.fetch(eid, fetch_fields)
                        if status != "OK":
                            continue

                        if body_needs_client_filter:
                            raw_email = msg_data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            body_text = self._extract_body(msg)
                        else:
                            header_data = msg_data[0][1]
                            msg = email.message_from_bytes(header_data)
                            body_text = ""

                        from_value = decode_header_value(msg.get("From", ""))
                        subject_value = decode_header_value(msg.get("Subject", ""))
                        date_value = msg.get("Date", "")

                        match = True
                        if sender and sender.lower() not in from_value.lower():
                            match = False
                        if subject_needs_client_filter and subject.lower() not in subject_value.lower():
                            match = False
                        if body_needs_client_filter and body_keyword.lower() not in body_text.lower():
                            match = False
                        
                        if (start_dt or end_dt) and date_value:
                            try:
                                from email.utils import parsedate_to_datetime
                                email_dt = parsedate_to_datetime(date_value)
                                email_dt = email_dt.replace(tzinfo=None)
                                if start_dt and email_dt < start_dt:
                                    match = False
                                if end_dt and email_dt > end_dt + timedelta(days=1):
                                    match = False
                            except Exception as e:
                                logger.warning(f"Failed to parse date '{date_value}': {e}")

                        if match:
                            matched_ids.append(eid)
                            logger.info(f"  Match: {subject_value} (from: {from_value})")

                    email_ids = matched_ids
                else:
                    email_ids = list(email_ids[-max_results:])
            else:
                status, messages = mail.search(None, 'ALL')
                all_ids = messages[0].split() if messages[0] else []
                logger.info(f"Total emails in folder: {len(all_ids)}")

                if subject_needs_client_filter or body_needs_client_filter:
                    matched_ids = []
                    scan_limit = min(len(all_ids), max(max_results * 100, 1000))
                    scan_ids = all_ids[-scan_limit:]
                    logger.info(f"Scanning last {len(scan_ids)} emails")

                    for eid in reversed(scan_ids):
                        if len(matched_ids) >= max_results:
                            break

                        status, msg_data = mail.fetch(eid, "(BODY.PEEK[])")
                        if status != "OK":
                            continue

                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        subject_value = decode_header_value(msg.get("Subject", ""))
                        body_text = self._extract_body(msg)

                        match = True
                        if subject_needs_client_filter and subject.lower() not in subject_value.lower():
                            match = False
                        if body_needs_client_filter and body_keyword.lower() not in body_text.lower():
                            match = False

                        if match:
                            matched_ids.append(eid)
                            logger.info(f"  Match: {subject_value}")

                    email_ids = matched_ids
                else:
                    email_ids = list(all_ids[-max_results:])

            results = []
            for eid in reversed(email_ids[:max_results]):
                status, msg_data = mail.fetch(eid, "(FLAGS RFC822)")
                if status != "OK":
                    continue

                flags_str = msg_data[0][0].decode() if isinstance(msg_data[0][0], bytes) else str(msg_data[0][0])
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject_decoded = decode_header_value(msg.get("Subject", ""))
                from_decoded = decode_header_value(msg.get("From", ""))
                to_decoded = decode_header_value(msg.get("To", ""))
                date_str = msg.get("Date", "")
                message_id = msg.get("Message-ID", "").strip()

                body = ""
                attachments_list = []

                if include_body or include_attachments:
                    body, attachments_list = self._extract_content(msg, include_attachments)

                has_replies = "\\Answered" in flags_str
                logger.debug(f"Email {eid} flags: {flags_str}, has_replies: {has_replies}")

                email_data = {
                    "id": eid.decode() if isinstance(eid, bytes) else str(eid),
                    "from": from_decoded,
                    "to": to_decoded,
                    "subject": subject_decoded,
                    "date": date_str,
                    "body_preview": body[:500] if body else "",
                    "has_attachments": len(attachments_list) > 0,
                    "has_replies": has_replies
                }

                if include_body:
                    email_data["body"] = body

                if attachments_list:
                    if include_attachments:
                        processed = []
                        for att in attachments_list:
                            att_info = {
                                "filename": att["filename"],
                                "content_type": att["content_type"],
                                "size": att["size"]
                            }
                            if attachment_format == "url":
                                try:
                                    upload_resp = self.session.file.upload(
                                        filename=att["filename"],
                                        content=att["_raw"],
                                        mimetype=att["content_type"]
                                    )
                                    att_info["upload_file_id"] = upload_resp.id
                                    att_info["url"] = upload_resp.preview_url or ""
                                    att_info["format"] = "url"
                                    logger.info(f"  Uploaded attachment '{att['filename']}' -> {upload_resp.id}")
                                except Exception as e:
                                    logger.warning(f"  Failed to upload attachment '{att['filename']}': {e}")
                                    att_info["content_base64"] = att["content_base64"]
                                    att_info["format"] = "base64"
                            else:
                                att_info["content_base64"] = att["content_base64"]
                                att_info["format"] = "base64"
                            processed.append(att_info)
                        email_data["attachments"] = processed
                    else:
                        email_data["attachments"] = [
                            {"filename": a["filename"], "content_type": a["content_type"], "size": a["size"]}
                            for a in attachments_list
                        ]

                results.append(email_data)
                logger.info(f"  Result: {subject_decoded} (from: {from_decoded})")

            mail.logout()
            logger.info(f"Returning {len(results)} emails")

            yield self.create_json_message({
                "total_found": len(results),
                "folder": folder,
                "emails": results
            })

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
            yield self.create_json_message({
                "error": f"IMAP error: {str(e)}",
                "total_found": 0,
                "emails": []
            })
        except Exception as e:
            logger.error(f"Search failed: {e}")
            yield self.create_json_message({
                "error": f"Failed to search emails: {str(e)}",
                "total_found": 0,
                "emails": []
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

    def _extract_body(self, msg: email.message.Message) -> str:
        body = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disp:
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    continue
                if content_type == "text/plain" and not body:
                    body = text
                elif content_type == "text/html" and not html_body:
                    html_body = text
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    text = ""
                if content_type == "text/plain":
                    body = text
                elif content_type == "text/html":
                    html_body = text

        if not body and html_body:
            body = html_to_plain_text(html_body)

        return body

    def _extract_content(self, msg: email.message.Message, include_attachments: bool) -> tuple[str, list[dict]]:
        body = ""
        html_body = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                if filename and include_attachments:
                    payload = part.get_payload(decode=True)
                    if payload:
                        filename_decoded = decode_header_value(filename)
                        attachments.append({
                            "filename": filename_decoded,
                            "content_type": content_type,
                            "size": len(payload),
                            "content_base64": base64.b64encode(payload).decode('utf-8'),
                            "_raw": payload
                        })
                    continue

                if "attachment" in content_disp:
                    continue

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    continue

                if content_type == "text/plain" and not body:
                    body = text
                elif content_type == "text/html" and not html_body:
                    html_body = text
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    text = ""
                if content_type == "text/plain":
                    body = text
                elif content_type == "text/html":
                    html_body = text

        if not body and html_body:
            body = html_to_plain_text(html_body)

        return body, attachments

    def _check_email_has_reply(self, mail: imaplib.IMAP4, message_id: str, folder: str) -> bool:
        if not message_id:
            logger.debug("No Message-ID, cannot check for replies")
            return False
        
        logger.info(f"Checking replies for Message-ID: {message_id}")
        
        try:
            sent_folder_names = [
                "Sent", "Sent Items", "Sent Messages", "[Gmail]/Sent Mail",
                "&U0zJzQ-", "已发送", "&V4lXPpCuTvY-",  # 飞书/网易等中文文件夹名
                "INBOX.Sent", "Sent Items"
            ]
            
            folders_to_check = [folder]
            
            try:
                status, folder_list = mail.list()
                if status == "OK":
                    for folder_info in folder_list:
                        if isinstance(folder_info, bytes):
                            folder_info = folder_info.decode('utf-8', errors='ignore')
                        for sent_name in sent_folder_names:
                            if sent_name.lower() in folder_info.lower():
                                if folder_info not in folders_to_check:
                                    folders_to_check.append(folder_info.strip('"'))
                                    logger.info(f"Found sent folder candidate: {folder_info}")
            except Exception as e:
                logger.warning(f"Failed to list folders: {e}")
            
            for sent_name in sent_folder_names:
                if sent_name not in folders_to_check:
                    folders_to_check.append(sent_name)
            
            logger.info(f"Will check folders: {folders_to_check}")
            
            for check_folder in folders_to_check:
                try:
                    status, _ = mail.select(check_folder, readonly=True)
                    if status != "OK":
                        logger.debug(f"Cannot select folder {check_folder}")
                        continue
                    
                    logger.info(f"Scanning folder: {check_folder}")
                    
                    status, all_messages = mail.search(None, 'ALL')
                    all_ids = all_messages[0].split() if all_messages[0] else []
                    
                    scan_limit = min(len(all_ids), 1000)
                    scan_ids = all_ids[-scan_limit:]
                    
                    logger.info(f"Scanning {len(scan_ids)} emails in {check_folder}")
                    
                    for eid in scan_ids:
                        try:
                            status, msg_data = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES)])")
                            if status != "OK":
                                continue
                            
                            header_data = msg_data[0][1]
                            reply_msg = email.message_from_bytes(header_data)
                            
                            in_reply_to = reply_msg.get("In-Reply-To", "").strip()
                            references = reply_msg.get("References", "").strip()
                            
                            if (in_reply_to and message_id in in_reply_to) or \
                               (references and message_id in references):
                                logger.info(f"Found reply in {check_folder}: In-Reply-To={in_reply_to}, References={references}")
                                mail.select(folder, readonly=True)
                                return True
                        except Exception as e:
                            logger.debug(f"Error checking email {eid}: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"Error scanning folder {check_folder}: {e}")
                    continue
            
            mail.select(folder, readonly=True)
            logger.info("No replies found")
            return False
        except Exception as e:
            logger.warning(f"Failed to check reply for message {message_id}: {e}")
            try:
                mail.select(folder, readonly=True)
            except Exception:
                pass
            return False
