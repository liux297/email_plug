import base64
import email
import imaplib
import logging
import os
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
            status, data = mail.select(folder, readonly=True)
            if status != "OK":
                yield self.create_json_message({
                    "error": f"Failed to select folder: {folder}",
                    "total_found": 0,
                    "emails": [],
                    "debug_account": email_account
                })
                return

            total_in_folder = data[0].decode() if data and data[0] else "unknown"
            logger.info(f"Folder selected, total emails: {total_in_folder}")

            # Always return debug info
            yield self.create_json_message({
                "debug_info": f"Connected as {email_account} to {imap_host}:{imap_port}, folder={folder}, total_emails={total_in_folder}",
                "total_found": 0,
                "emails": []
            })
            return

            if sender:
                criteria.append(f'FROM "{sender}"')

            if subject:
                if is_ascii_only(subject):
                    criteria.append(f'SUBJECT "{subject}"')
                else:
                    logger.info(f"Subject contains non-ASCII, will verify client-side: '{subject}'")

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
                email_ids = messages[0].split() if messages and messages[0] else []
                logger.info(f"IMAP server returned {len(email_ids)} results")
            else:
                status, messages = mail.search(None, 'ALL')
                email_ids = messages[0].split() if messages and messages[0] else []
                logger.info(f"No IMAP criteria, total emails in folder: {len(email_ids)}")

            # Client-side verification only NARROWS the server-side result set; it
            # must never re-widen with a fresh "ALL" search. Flag criteria such as
            # ANSWERED / UNSEEN can only be evaluated by the IMAP server, so we keep
            # the server results as the base and drop anything that does not truly
            # match sender / subject / date / body. Some servers (e.g. Feishu) apply
            # FROM/DATE loosely and return extra messages, so this pass is required.
            needs_client_verify = bool(sender) or bool(subject) or bool(body_keyword) or bool(start_dt) or bool(end_dt)
            if needs_client_verify:
                logger.info("Applying client-side verification over server results...")
                scan_limit = min(len(email_ids), max(max_results * 100, 1000))
                candidates = email_ids[-scan_limit:]
                logger.info(f"Verifying {len(candidates)} emails locally")

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
                    if subject and subject.lower() not in subject_value.lower():
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
                logger.info(f"After client-side verification: {len(email_ids)} results")
            else:
                email_ids = list(email_ids[-max_results:])

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
                                    preview_url = upload_resp.preview_url or ""
                                    
                                    relative_path = ""
                                    if preview_url:
                                        from urllib.parse import urlparse
                                        parsed = urlparse(preview_url)
                                        relative_path = parsed.path + ("?" + parsed.query if parsed.query else "")
                                    
                                    external_base = os.environ.get("FILES_URL") or os.environ.get("CONSOLE_WEB_URL") or ""
                                    if external_base and relative_path:
                                        att_info["url"] = external_base.rstrip("/") + relative_path
                                    else:
                                        att_info["url"] = preview_url
                                    att_info["relative_path"] = relative_path
                                    
                                    att_info["format"] = "url"
                                    logger.info(f"  Uploaded attachment '{att['filename']}' -> {upload_resp.id}, url: {att_info['url']}")
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
