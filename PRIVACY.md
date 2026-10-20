## Privacy Policy

### Data Collection

This plugin collects the following data:

- **Email credentials**: SMTP server address, port, email address, and password/app-specific password. These are stored locally within the Dify platform's encrypted credential storage.
- **Email content**: The plugin processes email body content and metadata (sender, recipient, subject, date) when searching or sending emails.

The plugin does NOT collect any personal data beyond what is required for email operations. No data is sent to any third-party service other than the configured SMTP/IMAP mail server.

### Data Usage

All collected data is used solely for the following purposes:

- **SMTP credentials** are used to authenticate with your mail server and send emails on your behalf.
- **IMAP credentials** are used to authenticate with your mail server and search/retrieve emails.
- **Email content** is processed in real-time and returned as tool output within Dify workflows.

No data is shared with, sold to, or stored by any third-party service. All email operations are performed directly between the plugin and your configured mail server.

### Data Retention

- Credentials are retained for the lifetime of the plugin installation and are removed when the plugin is uninstalled.
- Email data is processed in real-time and is not persisted beyond the scope of a single tool invocation.
- Users can delete all stored credentials by uninstalling the plugin from their Dify instance.

### Contact

For privacy-related questions or concerns, please open an issue on the plugin's GitHub repository.
