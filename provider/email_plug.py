import imaplib
import smtplib
import ssl
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class EmailPlugProvider(ToolProvider):

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        smtp_host = credentials.get("smtp_host", "")
        smtp_port = credentials.get("smtp_port", "")
        imap_host = credentials.get("imap_host", "")
        imap_port = credentials.get("imap_port", "993")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")
        smtp_encrypt = credentials.get("smtp_encrypt_method", "TLS")
        imap_encrypt = credentials.get("imap_encrypt_method", "SSL")

        if not smtp_host:
            raise ToolProviderCredentialValidationError("SMTP server is required")
        if not smtp_port:
            raise ToolProviderCredentialValidationError("SMTP port is required")
        if not imap_host:
            raise ToolProviderCredentialValidationError("IMAP server is required")
        if not email_account:
            raise ToolProviderCredentialValidationError("Email account is required")
        if not email_password:
            raise ToolProviderCredentialValidationError("Email password is required")

        try:
            smtp_port = int(smtp_port)
            imap_port = int(imap_port)
        except ValueError:
            raise ToolProviderCredentialValidationError("Port must be a valid number")

        timeout = 30
        ctx = ssl.create_default_context()

        # Validate SMTP
        try:
            if smtp_encrypt.upper() == "SSL":
                with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=timeout) as server:
                    server.login(email_account, email_password)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
                    if smtp_encrypt.upper() == "TLS":
                        server.starttls(context=ctx)
                    server.login(email_account, email_password)
        except smtplib.SMTPAuthenticationError as e:
            raise ToolProviderCredentialValidationError(f"SMTP authentication failed: {str(e)}")
        except smtplib.SMTPConnectError as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to SMTP server: {str(e)}")
        except smtplib.SMTPException as e:
            raise ToolProviderCredentialValidationError(f"SMTP error: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"SMTP validation failed: {str(e)}")

        # Validate IMAP
        try:
            if imap_encrypt.upper() == "SSL":
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=timeout)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=timeout)
                if imap_encrypt.upper() == "TLS":
                    mail.starttls()
            mail.login(email_account, email_password)
            mail.logout()
        except imaplib.IMAP4.error as e:
            raise ToolProviderCredentialValidationError(f"IMAP authentication failed: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"IMAP validation failed: {str(e)}")
