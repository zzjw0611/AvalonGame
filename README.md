# AvalonGame · 原生手机阿瓦隆

面向 Android / iOS 的 React Native + Expo 客户端，连接自建 FastAPI 服务器。不是浏览器页面，也不是 WebView 套壳。支持 5–10 人、真人 / 规则机器人 / API 大模型混合参赛，房主也可仅观战。

**当前交付是邀请制内测源码 MVP + 已成功构建的 Android ARM64 测试 APK，尚未部署到你的服务器。** 后端 **79 项测试**（含 PostgreSQL 18 迁移和重启恢复）、手机完整 TypeScript 检查、**8 项 Jest 测试**、Expo 依赖校验及 Android/iOS JavaScript bundle 导出已在 [GitHub CI](https://github.com/zzjw0611/AvalonGame/actions/runs/35843523599) 通过。[Android 原生构建](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433) 也已成功，APK 已取回并核对 SHA-256；但尚未做真机完整对局、iOS 原生构建或真实模型联调。详见 [验证记录](docs/VALIDATION.md)。

[查看 PR #1](https://github.com/zzjw0611/AvalonGame/pull/1) · [下载 Android 内测 artifact](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433/artifacts/10741951607) · [安装与校验说明](docs/ANDROID_INTERNAL.md)

源码位于 `feat/native-mobile-mvp` 分支，PR 未自动合并到 `main`。Android artifact 当前保留到 2026-10-07，可能需要登录 GitHub 下载；它不是永久发布地址。解压后安装 `avalon-arm64-internal.apk`，仅供 ARM64 Android 内测，使用公开测试签名，正式分发必须换成自己保管的签名。

## 改造来源与范围

选择性改造 [xqbjs/AvalonGame](https://github.com/xqbjs/AvalonGame) 的人数配置和阶段机制，保留 Apache-2.0 许可与署名。没有整体复制研究训练框架或网页界面；规则转移、授权视角、接口、存储、Prompt 和原生界面为本项目重构。对比过 Avalon-LLM、ProAvalon，未复制未明确授权的研究代码。详细定位和差异见 [上游审查](docs/UPSTREAM_AUDIT.md)。

关键修正：第五次连续否决判邪恶获胜，而非自动通过；梅林看不到莫德雷德，邪恶互认排除奥伯伦；派西维尔候选按座位排序；刺杀菜单不泄漏后台好人名单。

## 已实现

- 原生大厅、建房、逐席配置、房间号加入、公共观战、身份面板、讨论、队伍表决、秘密任务、刺杀、公开历史与结束亮牌。
- 经典 5–10 人，梅林 / 刺客固定；可配置派西维尔、莫甘娜、莫德雷德、奥伯伦，其余自动补普通角色。
- 服务器权威状态机；秘密票收齐后公布；各席独立视角；同请求重试幂等，不能修改已交密票。
- SQLite 本地 / PostgreSQL 部署、Alembic 迁移、持久化会话与房间；后台恢复、WebSocket 重连、HTTP 快照补偿。
- 服务端模型配置、八角色与分阶段中文 Prompt、严格动作菜单、最多两次模型请求、调用预算与规则兜底，结束后展示使用统计。
- AI 授权上下文包含本局公开角色数量、完整结构化提案/结算历史（含被否决提案），与发言共享事件编号；任务编号明确从 1 开始，玩家文本不进入受信指令。

**规则边界：** 仅经典顺序任务，不实现湖中仙女、Targeting、Big Box、超十人或无梅林局。顺序发言、最终全员陈述和超时自动行动是公开的 APP 协议，不冒充官方规定。[规则规格](docs/RULES.md)

## 获取源码

```bash
git clone --branch feat/native-mobile-mvp https://github.com/zzjw0611/AvalonGame.git
cd AvalonGame
```

## 本地运行后端

需要 Python 3.13。以下命令在项目根目录执行：

```bash
cd backend
python -m venv .venv
# Linux/macOS；Windows 改为 .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
```

本地默认 `sqlite:///./avalon.db`。不配置模型仍能用标注为“规则机器人”的座位完成对局。外网部署不要使用未设置邀请码的开发模式。

## 部署到自己的服务器

准备域名并将 DNS 指向服务器，开放 80/443；安装 Docker 和 Compose。

```bash
cp .env.example .env
# 编辑 .env：DOMAIN、POSTGRES_PASSWORD、ACCESS_CODE；密码建议独立随机十六进制串
# 模型可暂时留空，或配置 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY
docker compose up -d --build
docker compose logs --tail=100 api
```

手机中填写 `https://你的域名` 和服务器邀请码。仅网关开放宿主机端口，数据库和 API 不直接暴露。PostgreSQL 18 数据卷挂载到 `/var/lib/postgresql`。备份示例：

```bash
docker compose exec -T db pg_dump -U avalon -d avalon > avalon-backup.sql
```

部署细节、会话恢复限制和安全边界见 [部署说明](docs/DEPLOYMENT.md)。不要直接删除数据库卷，也不要在未实现跨进程房间协调前增加 Uvicorn worker。

## 安装手机开发环境与打包

使用 Node.js 24。手机依赖选用已核对的 Expo SDK 56 配套版本，不追踪 SDK 58 预览模板。

```bash
cd mobile
npm ci
npm run typecheck
npm test
npm run check:expo
npx eas-cli@latest login
npx eas-cli@latest build:configure
npx eas-cli@latest build --platform android --profile preview
```

`preview` 生成独立 Android APK，不依赖 Metro 开发服务器。需登录你自己的 Expo 账号并配置签名；本仓库不含账号、项目 ID 或私钥。`mobile/package-lock.json` 已从成功 Android 构建的实际 artifact 导入并校验，版本清单一致且 `npm ci` 检查通过；不是手写锁文件。锁文件导入完成后，一次性导入工作流已移除，正常 CI 仅有只读权限并使用 `npm ci`。

开发构建：`npx eas-cli@latest build --platform android --profile development`，安装后运行 `npm start`。本机有 Android SDK 时也可 `npm run android`。iOS 使用相应 `--platform ios` 构建，Ad Hoc 需要登记设备；TestFlight 使用 production 构建与 Apple 开发者签名流程。Windows 不提供本地 iOS 模拟器。

另有 `.github/workflows/android-preview.yml`：在 GitHub 构建独立 ARM64 Android 内测 APK。它使用 Expo 模板的公开测试签名，仅用于受控试用，不是正式发行签名；构建结果从对应 Actions 的 `avalon-android-arm64-internal` artifact 获取。该包不含服务器或模型秘密，需要连接你部署好的 HTTPS 游戏服务器。正式分发前必须改用自己保管的签名密钥。

安装包只接受 HTTPS 游戏服务器地址。开发模式可允许 HTTP；真机不要把 `localhost` 当成你的服务器地址。`EXPO_PUBLIC_API_URL` 仅用于可选预填游戏服务器地址，**绝不能放大模型 API Key**。

## 项目结构

```text
backend/app/rules.py       权威规则、动作菜单、身份视角
backend/app/agents.py      独立玩家 Prompt、模型适配和明确标识的规则兜底
backend/app/main.py        会话、房间、HTTP / WS、计时与 AI 调度
backend/app/storage.py     数据存储与事务
backend/tests/             规则、接口、整局机器人、迁移和模型 Mock 测试
mobile/app/                原生页面（Expo Router）
mobile/src/                协议、凭证、重连、界面与类型
mobile/package-lock.json  与成功 Android 构建一致的依赖锁
compose.yaml / Caddyfile   服务器部署
```

## 尚未完成的发布验收

真实模型服务联调与成本测量、用户服务器部署、数据库备份恢复和并发压测、iOS 原生编译及正式签名、手机真机体验验收。Android APK 构建成功和哈希一致不等于真机游戏验收。当前实现用于邀请制小规模内测，不宣称生产级、绝对抗注入或高并发容量。账户找回、推送、语音、自动清理/删房、同房重开和应用商店隐私合规页面不在本次 MVP 范围。

软件使用 Apache-2.0；保留 [NOTICE](NOTICE)。这是非官方玩家项目，未包含官方美术，软件许可不等于获得游戏商标或素材授权。
