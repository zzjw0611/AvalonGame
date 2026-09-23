# 本次验证记录

核对日期：2026-09-23。验证的是本分支源码，不是既有上游的完整产品认证。

| 范围 | 实际结果 |
|---|---|
| Python规则/API/迁移 | `cd backend && PYTHONPATH=. pytest -q`：65 passed |
| 完整规则机器人对局 | 5–10人各4个随机种子的规则层整局 + 各人数HTTP/API调度整局，包含于上述测试 |
| 模型接口 | HTTPX MockTransport 验证非法输出修复、两次请求上限、503兜底；未使用真实API密钥 |
| SQLite恢复 | 数据库重启后同会话/角色/阶段恢复，Alembic反复upgrade保持数据与模型一致 |
| 手机协议 | 8项纯函数检查在Node中运行通过，覆盖HTTPS地址、旧快照防回滚、聊天仍是数据 |
| TS/TSX | 10个文件经本地TypeScript 5.8.3语法转译通过；不是依赖感知类型检查 |
| 手机依赖安装 | npm请求返回EAI_AGAIN/DNS失败；没有完整依赖安装，也没有伪造package-lock |
| 原生/部署 | 未执行Android/iOS编译、APK/IPA签名、真机验收、真实PostgreSQL或Docker部署 |

规则测试包括：严格多数、第五次否决、特殊角色视野、派西维尔候选排序、7–10人第四任务双失败、好人禁失败牌、任务结果匿名、三胜后刺杀与三败终局、非法动作不修改状态、同请求不能改票。

接口测试包括：会话鉴权、非成员拒绝、座位不能伪造、真人席未满不能开局、密票期间他人视图完全不变、重复请求、WS重连与认证、断开时连接计数释放、真实持久化恢复、截止时间、邀请码、未配置模型拒绝、请求大小、会话撤销。

`.github/workflows/ci.yml` 已提供Python测试、安装手机依赖、完整tsc/Jest、Expo依赖检查及Android/iOS JS bundle导出。CI文件存在不等于执行已成功；以GitHub运行结果为准，bundle导出也不等于原生编译。Maestro真机冒烟脚本在 `mobile/.maestro/smoke.yaml`，本次未运行。

## 重新验证

```bash
cd backend
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
cd ../mobile
npm install
npm run typecheck
npm test
npm run check:expo
npx expo export --platform android --output-dir dist/android
npx expo export --platform ios --output-dir dist/ios
```

正式可试玩交付仍需：仓库所有者配置域名/服务器/模型服务，完成Expo项目与签名，然后独立安装包真机完整对局测试。当前不宣称全部需求已经以安装包形式交付。
