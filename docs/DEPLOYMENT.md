# 固定 IP 部署与升级（0.2.0）

## 网络与 HTTPS

目标服务器固定为 `42.193.181.239`，App 默认 API 根地址 `https://42.193.181.239`，WebSocket 自动使用同主机 `wss`。普通玩家不选择主机。此配置不证明实际端口、证书或服务已经运行。

打开服务器防火墙/安全组的 443/TCP；80/TCP 用于 HTTP 跳转或由你选用的 ACME 客户端验证证书。仅 Caddy 对外暴露，数据库和 API 留在 Compose 网络。不要把数据库直接开放到公网。

默认 `Caddyfile` **显式加载证书文件**，并为不发送 SNI 的 IP 客户端设置 `default_sni`。在服务器的 `certs/` 放入 `fullchain.pem`、`privkey.pem`，或用 `.env` 的 `TLS_CERT_DIR` 指定挂载目录。证书必须含 `IP Address:42.193.181.239` 的 SAN、未过期且可被手机系统信任。链文件和私钥不能提交 GitHub。

Caddy 对 IP 的默认本地证书不会自动获得所有手机信任，所以本项目不依赖这一默认行为。公开 IP 证书可通过支持它的 CA/ACME 客户端签发；Let's Encrypt 已提供 IP 短期证书，管理员必须自动续期并监控失败。这里没有替用户完成证书签发，也不提供虚假的可用证书。

更新文件后重新加载：

```sh
docker compose exec gateway caddy reload --config /etc/caddy/Caddyfile --force
```

外部验证：`curl --fail https://42.193.181.239/healthz`。不要加 `-k` 绕过证书错误作为验收。没有有效 TLS 时修复部署，不在客户端启用任意 HTTP 或信任所有证书。

参考：
- https://caddyserver.com/docs/automatic-https
- https://caddyserver.com/docs/caddyfile/directives/tls
- https://caddyserver.com/docs/caddyfile/options#default_sni
- https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/

## 配置和启动

复制 `.env.example` 为 `.env`。为 `POSTGRES_PASSWORD`、`ACCESS_CODE` 分别生成随机值：

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

密码建议十六进制以避免数据库 URL 转义问题。生产环境缺邀请码会拒绝启动。数据库卷必须备份，不要执行会删除数据的 `docker compose down -v`。

模型接口保留服务端环境配置：`LLM_BASE_URL` 是兼容接口根地址（通常含 `/v1`），客户端不填写它；`LLM_MODEL` 是提供商实际模型 ID，`LLM_API_KEY` 只在服务器。多个模型用 `LLM_PROFILES_JSON` 引用不同环境变量中的密钥；App 仅获取 profile ID/显示名称。

```sh
docker compose up -d --build
docker compose logs --tail=100 api
```

PostgreSQL 18 卷挂载 `/var/lib/postgresql`；启动 API 前运行 Alembic 迁移。Uvicorn 保持 **一个 worker**：目前房间锁/调度器是单进程，不能直接横向扩容。

## AI 故障不再有脚本兜底

只可创建 `human` 和 `llm` 座位；任何旧版客户端提交 `bot` 都返回 422。没有 profile 时仍可建立全真人房间，不可创建 AI 席位。

每次模型决策最多两次请求。模型错误、响应非法、超时或预算不足会暂停整间房：`status=PAUSED_AI`，保存剩余时间，保留角色/密票/阶段。暂停提示不含座位或牌值，也不含模型响应、密钥或异常堆栈。

房主调用 `POST /api/rooms/{code}/ai/retry` 恢复；其他用户无权限。不会清零预算。预算耗尽时管理员调整 `LLM_CALL_BUDGET` 并重启服务，然后房主重试；配置缺失时先修复环境变量。接口不保证供应商已经恢复，仍失败则再次暂停。

所有未完成请求有调度代次隔离，旧响应在暂停/恢复后不会代替新的行动；已花费调用仍计入统计。服务器重启后保留暂停状态。真人超时默认行为保持房间公示，但不会用于代替 AI。

## 从 0.1.0 升级

先备份：

```sh
docker compose exec -T db pg_dump -U avalon -d avalon > avalon-backup.sql
```

在维护窗口更新后端和 0.2.0 手机包。含原规则机器人席位的未结束房间自动变成只读 `ARCHIVED`，不删除历史或角色，不自动替换为收费 AI；已结束房间保留复盘。旧版其他房间可保留，但建议新开房间验证版本一致。

原来其他主机保存的会话不会被转发给固定 IP；同主机凭证可恢复。不要为迁移让用户把 token 或 API Key 贴进聊天或仓库。

## 验收边界

CI 的模拟模型响应不是实际提供商联调；源码测试/编译不等于真机整局、TLS 部署或并发压测。当前仍为邀请制内测。语音、推送、账号找回、同房重开及公开上线的隐私流程尚未实现。
