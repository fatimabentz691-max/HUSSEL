# Token Manager 安装与卸载

## 系统要求

- Windows 10 1903 或更高版本、Windows 11；
- 64 位 x86 处理器；
- Microsoft Edge WebView2 Runtime；
- 至少 150 MB 可用磁盘空间。

## 安装版

1. 在 GitHub Releases 下载最新的 `TokenManager_*_x64-setup.exe`。
2. 双击安装包，根据向导完成安装。
3. 从开始菜单打开 Token Manager。
4. 如果 Windows SmartScreen 提示未知发布者，请确认文件来自本仓库 Release，并核对 Release 页面公布的 SHA256。未签名版本不建议从第三方网盘下载。

安装不会自动读取浏览器密码，也不会修改系统代理。

## 便携版

便携 EXE 适合开发测试。API Key 仍使用当前 Windows 用户的 DPAPI，因此把 EXE 复制到另一台电脑不会自动获得原电脑密钥。跨电脑迁移请使用设置页的“本地加密迁移”。

## 数据位置

默认数据库：

```text
%LOCALAPPDATA%\Token Manager\token-manager.db
```

界面布局、悬浮窗配置等少量状态由 WebView2 本地存储保存。导出迁移包时，两类数据会一起处理。

## 卸载

1. 打开 Windows“设置 → 应用 → 已安装的应用”。
2. 找到 Token Manager 并选择卸载。
3. 如需彻底删除历史数据，再手动删除 `%LOCALAPPDATA%\Token Manager`。

卸载前建议先从设置页导出 `.tmbak` 加密迁移包。

## 常见安装问题

### 应用打开后白屏

安装或修复 Microsoft Edge WebView2 Runtime，然后重新启动应用。若仍有问题，请提交系统版本、WebView2 版本和脱敏截图，不要上传 API Key 或数据库原文件。

### Windows 阻止运行

当前社区构建可能未配置商业代码签名。只从本仓库 Release 下载并核对 SHA256；无法确认来源时请勿运行。

### 悬浮窗看不到内容

先升级到最新版本，再在设置页关闭并重新开启悬浮窗。窗口布局异常时，可切换迷你模式或重新选择卡片网格。
