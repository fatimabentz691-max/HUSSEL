# 安全策略

## 支持范围

安全修复优先提供给最新版本。报告问题前请先确认是否能在最新 Release 复现。

## 私密报告安全问题

请优先使用 GitHub 仓库的 Security Advisories 私密报告功能。不要在公开 Issue 中提交以下内容：

- API Key、Access Key、Secret Key；
- `.tmbak` 迁移包；
- `token-manager.db` 数据库；
- 完整请求或响应正文；
- 包含用户目录、会话文本或组织信息的日志。

报告应包含受影响版本、Windows 版本、复现步骤、预期影响和已完成的脱敏处理。

## 安全边界

- 密钥使用 Windows DPAPI 绑定当前用户加密；
- 本地代理只绑定 `127.0.0.1`；
- 上游默认必须为 HTTPS，本机调试地址除外；
- 代理不持久化请求正文、响应正文或 Authorization；
- Codex 读取逻辑只提取 Token、时间、模型和任务分类字段。

## 不属于漏洞的情况

- 未签名社区构建触发 SmartScreen；
- Codex 本地预算估算与官方客户端额度不同；
- 厂商 API Key 缺少账单权限；
- 用户主动把迁移包或 API Key 公开给第三方。
