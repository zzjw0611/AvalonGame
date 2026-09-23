# Android 内测构建与本次续作

核验日期：2026-09-23。源码已在 `feat/native-mobile-mvp`；[PR #1](https://github.com/zzjw0611/AvalonGame/pull/1) 未自动合并。

## 已生成的独立 Android 构建

[Android 构建 run 35840675433](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433) 的 `apk` job 已完成且结论为 **success**。Gradle 原生编译、收集产物和上传步骤均成功，不只是 JavaScript 导出。

- [直接打开 artifact 下载页](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433/artifacts/10741951607)
- 名称：`avalon-android-arm64-internal`
- artifact ID：`10741951607`
- 构建源码：`ac70081fc719998e1d813a1dc165ab28433d02fd`
- GitHub 返回的压缩 artifact 大小：23,714,007 字节；这不是单独 APK 文件大小。
- GitHub 返回的 artifact 摘要：`sha256:2ce0f33cb5f4ce9777eb5aa89b3890d78ee58b50776682e394a2f87ef95c7745`。它不是对单独 APK 的重新计算值。
- 当前保留至：2026-10-07 09:16:52 UTC；下载可能需要登录 GitHub。到期后需重新运行构建，不能把临时 artifact 当作永久发布地址。

下载并解压 artifact 后，取其中 APK 在兼容 ARM64 Android 设备上内测。此构建使用 Expo 模板公开测试签名；不是正式发行签名，不用于商店发布或可信生产分发。不会安装 iOS；也不包含服务器或模型服务。

本次只通过 GitHub 构建状态和 artifact 元数据确认原生产物存在，尚未把 APK 安装到真实手机验证，未将压缩 artifact 下载到本地重新校验。安装成功和完整游戏体验仍需真机验收。

## 连接游戏

先按 [部署文档](DEPLOYMENT.md) 在自己的服务器启动后端，配置域名、HTTPS 和服务器邀请码；模型密钥仅写服务器 `.env`，不提交 GitHub。打开 App 填写该 HTTPS 服务器地址、昵称和邀请码。先用规则机器人检查网络与流程，再启用已配置的 LLM profile。

`localhost` 指当前手机，不是你的云服务器。安装包不依赖 Expo Go 或 Metro，但联网对局依赖实际运行的后端。

## 本次 AI 上下文修复

- 授权视角增加从公开房间配置推导的 `role_counts`，不是洗牌后的座位身份表。
- Prompt 保留被否决提案的队伍、队长、尝试次数及其公开投票事件，使用共同 `seq` 对齐发言和事件。
- 传给模型的任务编号改为明确的 `quest_number`（从 1 开始）；规则引擎与手机协议继续使用原有零基索引。
- 公开结构化事件采用类型和字段白名单；玩家发言保持在低权限数据消息中，未知扩展事件不会自动进入受信 Prompt。
- 新增 `backend/tests/test_prompt_context.py`，覆盖 5–10 人公开角色数量、隐藏身份置换不变性、密票隔离、历史提案和发言窗口等。

这些改动在后端生效，不需要为此更换已有手机安装包。测试结果以本次提交对应的 GitHub CI 为准；实际模型质量、API 兼容性与费用仍需使用用户自己的模型服务验证。
