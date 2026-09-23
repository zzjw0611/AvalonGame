# Android 内测安装与构建

核验日期：2026-09-23。源码已在 `feat/native-mobile-mvp`；[PR #1](https://github.com/zzjw0611/AvalonGame/pull/1) 未自动合并。

## 已生成的独立 Android APK

[Android 构建 run 35840675433](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433) 的 `apk` job 已完成且结论为 **success**。Gradle 原生编译、收集产物和上传步骤均成功，不只是 JavaScript 导出。

[打开 artifact 下载页](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433/artifacts/10741951607)，下载 `avalon-android-arm64-internal`，解压并取出 `avalon-arm64-internal.apk`。

| 项目 | 值 |
|---|---|
| 构建源码 | `ac70081fc719998e1d813a1dc165ab28433d02fd` |
| artifact ID | `10741951607` |
| 压缩 artifact 大小 | 23,714,007 字节 |
| APK 文件大小 | 39,621,916 字节 |
| 当前 artifact 保留期限 | 2026-10-07 09:16:52 UTC |
| 平台 | ARM64 Android；不是 iOS 安装包 |

下载可能需要登录 GitHub，到期后需重新构建，临时 artifact 不是永久发布地址。

## 已实际核对的 SHA-256

整个 artifact ZIP：

```text
2ce0f33cb5f4ce9777eb5aa89b3890d78ee58b50776682e394a2f87ef95c7745
```

其中 APK：

```text
3b2dc43d6a1a8e5fd33539c83d1c1f520095d7eebafbe07e3149e53d27c32fd2
```

已下载、解压并计算以上两个摘要；分别与 GitHub artifact 元数据和包内 `SHA256SUMS.txt` 一致。APK ZIP CRC 检查通过，包含 `lib/arm64-v8a/libreactnative.so`、Hermes 原生库和 `assets/index.android.bundle`。这确认文件完整性，不等于已在真实手机安装或完成游戏体验测试。

Linux 校验 APK：

```bash
sha256sum avalon-arm64-internal.apk
```

此构建使用 Expo 模板公开测试签名；不是正式发行签名，不用于商店发布或可信生产分发。发布前应重新构建并使用自己保管的签名密钥。不要把校验值一致误认为代码或签名已经通过独立安全审计。

## 连接游戏

先按 [部署文档](DEPLOYMENT.md) 在自己的服务器启动后端，配置域名、HTTPS 和服务器邀请码。模型密钥仅写服务器 `.env`，不提交 GitHub。打开 App 填写 HTTPS 服务器地址、昵称和邀请码；先使用规则机器人检查网络与流程，再启用已配置的 LLM profile。

`localhost` 指当前手机，不是云服务器。这个 APK 不依赖 Expo Go 或 Metro，但联网对局需要实际运行的后端；用户的服务器尚未由本次任务部署。

## 续作改动及兼容性

公开角色数量、被否决的历史队伍与票型、明确任务编号、受信事件白名单等 Prompt 修复均在后端生效，不需要为这些后端更新更换已有手机安装包。原有手机协议字段保持兼容。

与成功 Android 构建相同的实际依赖锁已导入 `mobile/package-lock.json`，并经过清洁安装检查。iOS 原生构建、真实模型联调和真机完整对局仍为未完成验收项。
