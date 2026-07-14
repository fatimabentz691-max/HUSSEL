# 日志与密钥安全

日志发现器只扫描用户主动启用的 Codex、Claude Code、Cursor 本地目录，采用增量文件监听和 JSONL 流式解析。解析后立即提取 token 字段并丢弃原始正文；无法识别的版本会标为“需更新解析器”。

Windows 端密钥保存应使用 DPAPI `CryptProtectData`/`CryptUnprotectData`，并绑定当前登录用户。便携版不应复制解密后的密钥；迁移账户时只导出不含密钥的配置文件。

本地代理必须绑定 loopback 地址，拒绝局域网访问，禁止记录 Authorization、请求 body、响应 body 及工具调用参数。代理记录只包含完成后可得到的模型、token 汇总、HTTP 状态和耗时。
