## Email Plug 邮件插件

**作者:** liux297
**联系:** 297218348@qq.com
**仓库:** https://github.com/liux297/email_plug
**版本:** 0.0.3
**类型:** tool

### 描述

完整的 Dify 邮件操作插件，通过 SMTP/IMAP 协议提供七个工具：

- **发送邮件**: 支持 HTML、抄送/密送、附件、多收件人
- **检索邮件**: 按发件人、主题、正文关键词、时间范围、读取状态高级搜索
- **获取附件**: 从邮件下载附件或列出所有附件
- **标记邮件**: 标记邮件为已读或未读
- **删除邮件**: 删除邮件（移至回收站或永久删除）
- **移动邮件**: 在文件夹之间移动邮件
- **列出文件夹**: 列出所有可用的邮件文件夹

### 配置

1. 在 Dify 实例中安装插件
2. 配置以下凭证：

**SMTP 配置（用于发送）：**
| 字段 | 必填 | 说明 |
|------|------|------|
| SMTP 服务器 | 是 | 例如 `smtp.gmail.com` |
| SMTP 端口 | 是 | 例如 `587`（TLS）、`465`（SSL） |
| SMTP 加密方式 | 是 | START TLS、SSL 或无加密 |

**IMAP 配置（用于接收/搜索）：**
| 字段 | 必填 | 说明 |
|------|------|------|
| IMAP 服务器 | 是 | 例如 `imap.gmail.com` |
| IMAP 端口 | 否 | 默认 `993`（SSL）、`143`（TLS） |
| IMAP 加密方式 | 否 | 默认 SSL |

**账号：**
| 字段 | 必填 | 说明 |
|------|------|------|
| 邮箱地址 | 是 | 用于认证的邮箱 |
| 密码 | 是 | 密码或应用专用密码 |

> **Gmail**: 需要生成[应用专用密码](https://support.google.com/accounts/answer/185833)
> **QQ 邮箱**: 使用授权码而非登录密码
> **Outlook**: IMAP 服务器是 `outlook.office365.com`

### 工具说明

#### 发送邮件 (send_email)
高级邮件发送功能：
- 多收件人（逗号分隔）
- 抄送 (CC) 和密送 (BCC)
- HTML 或纯文本正文
- 自定义发件人名称
- 文件附件（base64 编码）

#### 检索邮件 (search_email)
强大的邮件搜索过滤器：
- 文件夹选择（INBOX、Sent、Archive 等）
- 发件人筛选（支持部分匹配）
- 主题关键词（支持中文/非 ASCII）
- 正文关键词搜索
- 时间范围（start_date、end_date）或最近天数
- 仅未读过滤
- 可选附件获取

#### 获取附件 (get_attachment)
从邮件下载附件：
- 列出所有附件（设置 attachment_index 为 -1）
- 按索引下载指定附件
- 支持可配置的文件大小限制（默认 10MB）
- 返回 base64 编码内容

#### 标记邮件 (mark_email)
使用搜索结果中的邮件 ID 标记邮件为已读或未读。

#### 删除邮件 (delete_email)
两种删除模式：
- 标准：移至回收站（可恢复）
- 永久：立即删除（不可恢复）

#### 移动邮件 (move_email)
在文件夹之间移动邮件（例如 INBOX → Archive）。

#### 列出文件夹 (list_folders)
发现邮箱中所有可用的文件夹名称。

### 使用示例

**发送 HTML 邮件并抄送：**
```
to_email: john@example.com,jane@example.com
cc_email: manager@example.com
subject: 周报
body: <h1>报告</h1><p>详细内容...</p>
body_type: html
```

**搜索最近 7 天的未读邮件：**
```
folder: INBOX
days: 7
unread_only: true
max_results: 20
```

**按时间范围搜索并匹配正文关键词：**
```
start_date: 2024-01-01
end_date: 2024-01-31
body_keyword: 发票
```

### 常用 IMAP/SMTP 服务器

| 服务商 | SMTP | IMAP |
|--------|------|------|
| Gmail | smtp.gmail.com:587 | imap.gmail.com:993 |
| Outlook | smtp.office365.com:587 | outlook.office365.com:993 |
| QQ 邮箱 | smtp.qq.com:465 | imap.qq.com:993 |
| 163 邮箱 | smtp.163.com:465 | imap.163.com:993 |
| Yahoo | smtp.mail.yahoo.com:587 | imap.mail.yahoo.com:993 |
