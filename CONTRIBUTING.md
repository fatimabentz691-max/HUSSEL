# 参与贡献

感谢帮助改进 Token Manager。

## 开始之前

1. 先搜索现有 Issue，避免重复提交。
2. 功能请求请说明目标平台、官方文档链接、权限要求和期望数据字段。
3. 涉及供应商计价或账单接口时，只接受可追溯的官方资料。
4. 不要提交真实密钥、会话正文或未脱敏账单。

## 本地验证

```powershell
npm install
npm run build
cargo test --manifest-path src-tauri/Cargo.toml
```

涉及 Windows 窗口、托盘、通知、DPAPI 或代理的变更还应运行：

```powershell
npm exec tauri dev
```

## Pull Request 要求

- 一个 PR 解决一个清晰问题；
- 描述数据来源、隐私影响和失败回退；
- 新平台适配器遵循 [适配器开发规范](docs/adapter-development.md)；
- UI 文案必须区分官方余额、本地代理、账单导入和本地估算；
- 新功能需要中文说明和必要测试。
