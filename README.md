## Email Plug

**Author:** liux297
**Contact:** 297218348@qq.com
**Repository:** https://github.com/liux297/email_plug
**Version:** 0.0.2
**Type:** tool

### Description

A complete Dify plugin for email operations via SMTP/IMAP protocols. It includes seven tools:

- **Send Email**: Send emails with HTML support, CC/BCC, attachments, and multiple recipients
- **Search Email**: Advanced search by sender, subject, body keyword, date range, and read status
- **Get Attachment**: Download attachments from emails or list all attachments
- **Mark Email**: Mark emails as read or unread
- **Delete Email**: Delete emails (move to trash or permanent delete)
- **Move Email**: Move emails between folders
- **List Folders**: List all available mail folders

### Setup

1. Install the plugin in your Dify instance.
2. Configure the following credentials:

**SMTP Configuration (for sending):**
| Field | Required | Description |
|-------|----------|-------------|
| SMTP Server | Yes | e.g. `smtp.gmail.com` |
| SMTP Port | Yes | e.g. `587` (TLS), `465` (SSL) |
| SMTP Encryption | Yes | START TLS, SSL, or NONE |

**IMAP Configuration (for receiving/searching):**
| Field | Required | Description |
|-------|----------|-------------|
| IMAP Server | Yes | e.g. `imap.gmail.com` |
| IMAP Port | No | Default: `993` (SSL), `143` (TLS) |
| IMAP Encryption | No | Default: SSL |

**Account:**
| Field | Required | Description |
|-------|----------|-------------|
| Email Address | Yes | Your email for authentication |
| Password | Yes | Password or app-specific password |

> **Gmail**: Generate an [App Password](https://support.google.com/accounts/answer/185833)
> **QQ Mail**: Use authorization code instead of login password
> **Outlook**: IMAP server is `outlook.office365.com`

### Tools

#### Send Email
Send emails with advanced features:
- Multiple recipients (comma-separated)
- CC and BCC support
- HTML or plain text body
- Custom sender name
- File attachments (base64 encoded)

#### Search Email
Powerful email search with filters:
- Folder selection (INBOX, Sent, Archive, etc.)
- Sender filter (supports partial match)
- Subject keyword (supports Chinese/non-ASCII)
- Body keyword search
- Date range (start_date, end_date) or recent days
- Unread only filter
- Optional attachment retrieval

#### Get Attachment
Download attachments from emails:
- List all attachments (set attachment_index to -1)
- Download specific attachment by index
- Supports files up to configurable size limit (default 10MB)
- Returns base64 encoded content

#### Mark Email
Mark emails as read or unread using email IDs from search results.

#### Delete Email
Delete emails with two modes:
- Standard: Move to trash (recoverable)
- Permanent: Expunge immediately (unrecoverable)

#### Move Email
Move emails between folders (e.g., INBOX → Archive).

#### List Folders
Discover all available folder names in your mailbox.

### Usage Examples

**Send HTML email with CC:**
```
to_email: john@example.com,jane@example.com
cc_email: manager@example.com
subject: Weekly Report
body: <h1>Report</h1><p>Details here...</p>
body_type: html
```

**Search unread emails from last 7 days:**
```
folder: INBOX
days: 7
unread_only: true
max_results: 20
```

**Search by date range with body keyword:**
```
start_date: 2024-01-01
end_date: 2024-01-31
body_keyword: invoice
```

### Common IMAP/SMTP Servers

| Provider | SMTP | IMAP |
|----------|------|------|
| Gmail | smtp.gmail.com:587 | imap.gmail.com:993 |
| Outlook | smtp.office365.com:587 | outlook.office365.com:993 |
| QQ Mail | smtp.qq.com:465 | imap.qq.com:993 |
| 163 Mail | smtp.163.com:465 | imap.163.com:993 |
| Yahoo | smtp.mail.yahoo.com:587 | imap.mail.yahoo.com:993 |
