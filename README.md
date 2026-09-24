# AvalonGame · 手机阿瓦隆

Android / iOS 使用 React Native + Expo，后端使用 FastAPI + PostgreSQL。
源码在 `feat/native-mobile-mvp` 分支，PR #1 未自动合并。

## 0.2.0：固定服务器，仅真人与 AI

App 默认连接 **`https://42.193.181.239`（443 端口）**。普通玩家只输入昵称及必要的内测邀请码，不需要填写服务器或模型密钥。
创建房间选择 **5–10 人总数、真人席位数、角色配置**；剩余席位自动计为 AI 玩家。真人数量包含参赛房主；关闭房主参赛可全 AI 观战。把八位房间号发给好友即可远程加入，不要求同一 Wi-Fi。

**规则机器人选项、后端类型和脚本决策已移除。** 只有 `human` 与 `llm` 两种可创建的座位。AI 未配置时明确提示，可改为全真人对局；不会将脚本当作大模型。AI 调用失败、超时或预算不足时进入 `PAUSED_AI`，冻结行动时限，由房主重试；不会偷偷代投或代发言。

重试保留角色、已交密票、请求编号和调用预算，并作废暂停前仍在飞行中的 AI 响应。AI 所有行动（包括只有成功牌这一合法选项的阶段）使用模型请求，避免通过调用路径额外暴露身份。真人超时仍按已公示的房间协议处理；这不是机器人玩家。

原先含已移除座位类型的未结束房间只读归档，不删除历史，不自动转为收费 AI。已结束对局仍可复盘。

## 当前验证边界

本次修改的本地后端检查：**92 passed, 1 skipped**，跳过的是需要独立 PostgreSQL 实例的集成测试。最终云端状态查看 [Actions](https://github.com/zzjw0611/AvalonGame/actions)。类型/Jest/双平台 JS 打包与 Android APK 有工作流；只有实际成功的 run 才能作为产物依据。

**旧的 0.1.0 APK 不含本次 UI 与固定服务器配置，必须安装新构建。** 不把原版 APK 重新命名为新版。没有在用户服务器部署，没有真实模型密钥、真机整局或 iOS 原生签名验收。

## 服务器部署

```sh
git clone --branch feat/native-mobile-mvp https://github.com/zzjw0611/AvalonGame.git
cd AvalonGame
cp .env.example .env
```

在服务器上编辑 `.env`：设置独立随机 `POSTGRES_PASSWORD` 和 `ACCESS_CODE`，以及模型的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`。`PUBLIC_HOST` 默认已是 `42.193.181.239`。

**启动网关前必须准备受手机信任且覆盖该 IP 的证书**：放入 `certs/fullchain.pem`、`certs/privkey.pem`。默认 Caddy 配置加载这两个文件，不使用自签名证书冒充公网 HTTPS，不禁用客户端证书校验。证书及密钥均已在 `.gitignore` 排除。

```sh
docker compose up -d --build
docker compose logs --tail=100 api
curl --fail https://42.193.181.239/healthz
```

最后一条命令是在你的环境验收，不表示此 IP 已上线。详细配置、证书续期、暂停与旧数据处理见 [部署说明](docs/DEPLOYMENT.md)。

## 本地开发与测试

后端：Python 3.13；SQLite 仅用于本地。公网部署使用邀请码和 PostgreSQL。

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
PYTHONPATH=. pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
```

手机：Node.js 24 与已锁定的 Expo 配套依赖。

```sh
cd mobile
npm ci
npm run typecheck
npm test
npm run check:expo
npx eas-cli@latest build --platform android --profile preview
```

服务器默认值在 `mobile/src/config.ts`。只有开发者构建时可通过 `EXPO_PUBLIC_API_URL` 覆盖为开发环境；用户界面无地址选项，旧主机的会话不会发送到新主机。**这里不能放模型 API Key。**

GitHub Android 内测工作流生成独立 ARM64 APK，使用公开测试签名，只限内测。正式分发改为自己保管的签名；iOS 需要 Apple 签名配置。新版本号 0.2.0 / Android versionCode 2。

## 目录与范围

- `backend/app/rules.py`：确定性规则与授权视角。
- `backend/app/agents.py`：分角色/阶段 Prompt、模型调用与输出校验，无脚本玩家。
- `backend/app/runtime.py`：模型调度、暂停/恢复、预算、过期响应隔离。
- `backend/app/main.py`：会话、房间、真人动作及 WebSocket。
- `mobile/app/`：原生大厅、创建房间、对局及复盘。
- `mobile/src/roomSetup.ts`：人数计算与配置校验。

仅经典顺序任务；固定梅林/刺客，可配派西维尔、莫甘娜、莫德雷德、奥伯伦。不含扩展/超十人/语音/推送。顺序讨论、全员最终陈述和真人超时处理是 App 协议，见 [规则说明](docs/RULES.md)。

选择性改造 `xqbjs/AvalonGame`，保留 Apache-2.0 许可与署名。详细差异见 [上游审查](docs/UPSTREAM_AUDIT.md)；没有复制未明确授权研究代码或官方美术。保留 [LICENSE](LICENSE) / [NOTICE](NOTICE)。
