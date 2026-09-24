> **历史记录：以下为 0.1.0。0.2.0 已变更固定服务器与真人/AI 配置，旧 APK 不包含新界面。最新验证见 PR #1 与 Actions 的对应提交；不能用旧产物代替新版。**

# 验证记录

核对日期：2026-09-23。验证的是本分支源码，不是上游项目的产品认证，也不是实际手机或生产环境验收。

## 已实际通过

[源码 CI run 35843523599](https://github.com/zzjw0611/AvalonGame/actions/runs/35843523599)，PR head `e4d0ea1a376f4c95959447fd5d75aeaa2ec76842`，对应 PR 合并测试提交 `400923461354c65ff58d7751f376a865d0604502`。

| 范围 | 实际结果 |
|---|---|
| Python 规则/API/迁移/Prompt | **79 passed, 1 warning**；CI 使用 PostgreSQL 18 容器。警告为依赖库弃用提示，并非测试失败 |
| 完整规则机器人对局 | 5–10 人各 4 个随机种子的规则层整局，以及各人数 HTTP/API 调度整局，包含于上述测试 |
| AI 上下文回归 | 新增 13 个测试实例；公开角色数量、身份置换不变性、被否决提案、密票隔离、任务编号、受信事件白名单与发言窗口 |
| 模型接口 | HTTPX MockTransport 验证非法输出、两次请求上限和 503 兜底；没有使用真实 API 密钥 |
| 数据库恢复 | SQLite 与 PostgreSQL 18 测试验证会话/角色/阶段恢复、事务保存和 Alembic 迁移；没有验证用户服务器的备份恢复或容量 |
| 手机协议 | 8 项 Jest 测试；HTTPS 地址、旧快照防回滚、聊天保持数据等 |
| TypeScript | 实际依赖安装后的 `tsc --noEmit` 通过 |
| Expo 依赖 | 配套版本兼容检查通过 |
| Android/iOS JS | 两个平台的 `expo export` 均成功；不是 iOS 原生编译 |
| Android 原生 | [run 35840675433](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433) 的 Gradle `assembleRelease` 和 artifact 上传成功 |
| Android 产物完整性 | 已下载 artifact，ZIP 和其中 APK 的 SHA-256 均匹配记录；APK ZIP CRC 检查通过，包含 ARM64 原生库与离线 JS bundle |

`mobile/package-lock.json` 已从上述成功 Android 构建的真实 artifact 导入（提交 `3445559b21779bc868c7a9c2a6f6faf328b663f5`）；SHA-256 为 `6b1b6296fa42b6ebdff2150e5a912a5e73aea2909d44f25b4df7b6faadc44886`。一次性导入先比较 package.json 的运行时和开发依赖，随后运行 `npm ci`、TypeScript、Jest 和 Expo 兼容检查，再仅提交锁文件。导入工作流已完成使命并移除，不保留不必要的写入权限。正常 CI 使用 `npm ci`。

## 规则及安全覆盖

严格多数、第五次否决、特殊角色视野、派西维尔候选排序、7–10 人第四任务双失败、好人禁失败牌、任务结果匿名、三胜后刺杀与三败终局、非法动作不修改状态、同请求不能改票。

接口测试包括会话鉴权、非成员拒绝、座位不能伪造、真人席未满不能开局、密票期间他人视图不变、重复请求、WS 重连与认证、断开时连接计数释放、持久化恢复、截止时间、邀请码、未配置模型拒绝、请求大小、会话撤销。

AI 上下文的公开角色组成来自房间配置，不是洗牌身份数组。结构化事件和低权限发言用共同 seq 对齐；不能把历史中新增的未知事件自动提升为系统事实。这些措施和测试不构成绝对抗提示词注入保证。

## 重跑

```bash
cd backend
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
cd ../mobile
npm ci
npm run typecheck
npm test
npm run check:expo
npx expo export --platform android --output-dir dist/android
npx expo export --platform ios --output-dir dist/ios
```

本地未设置 `POSTGRES_TEST_URL` 时 PostgreSQL 集成测试会跳过；配置后只可指向可丢弃的测试数据库，不能使用生产数据库。初版历史记录为本地 65 项通过、CI 66 项通过；续作增加 13 项后为 79 项，不能混淆测试版本。

## 仍未验证

Android 真机完整对局、Maestro 实机冒烟（脚本在 `mobile/.maestro/smoke.yaml`）、iOS 原生编译/Apple 签名/设备安装、真实模型 API 兼容性与成本、用户服务器 Docker 部署、备份恢复、并发和安全压测。

Android 内测 APK 使用公开测试签名，仅 ARM64；不能安装到 iOS，也不是正式可信发行包。详细下载、APK 摘要与保留期限见 [ANDROID_INTERNAL.md](ANDROID_INTERNAL.md)。
