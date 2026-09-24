# 服务器证书目录

在部署机器上放入 `fullchain.pem` 与 `privkey.pem`，不要提交真实文件。
证书必须由设备信任的 CA 签发，subjectAltName 含 `IP Address:42.193.181.239`。
默认网关只加载这些文件，不会把自签名证书当作公网可用证书。
证书续期由管理员的 ACME 客户端自动执行；更新文件后执行：

```sh
docker compose exec gateway caddy reload --config /etc/caddy/Caddyfile --force
```

私钥设置最小权限，并保证 Caddy 容器可读取。不要关闭 App 的证书校验。
