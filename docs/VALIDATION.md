# 本次验证记录

核对日期：2026-09-23。验证的是本分支源码，不是既有上游的完整产品认证。

| 范围 | 实际结果 |
|---|---|
| Python规则/API/迁移 | 本地 `PYTHONPATH=. pytest -q`：65 passed, 1 skipped（本地无PostgreSQL）；GitHub配置PostgreSQL 18后66项通过 |
| 完整规则机器人对局 | 5–10人各4个随机种子的规则层整局 + 各人数HTTP/API调度整局，包含于上述测试 |
| 模型接口 | HTTPX MockTransport 验证非法输出修复、两次请求上限、503兜底；未使用真实API密钥 |
| 数据库恢复 | SQLite本地及PostgreSQL 18 CI均验证会话/角色/阶段重启恢复、事务保存和Alembic迁移；未做用户服务器备份恢复与并发压测 |
| 手机协议 | 本地Node纯函数8项通过；GitHub的真实Jest运行同样8项通过，覆盖HTTPS地址、旧快照防回滚、聊天仍是数据 |
| TS/TSX | 本地10个文件语法转译通过；随后GitHub安装真实依赖并通过TypeScript 6完整`tsc --noEmit` |
| 手机依赖安装 | 本地npm DNS失败；GitHub随后成功安装并通过Expo版本兼容检查，生成的实际package-lock保存在CI artifact；没有伪造锁文件 |
| Android/iOS JS打包 | GitHub已分别成功执行两个平台的`expo export`；不等于原生编译或真机测试 |
| 原生/部署 | Android原生内测包独立构建见下方记录；iOS编译/正式签名、真机验收、用户服务器Docker部署及备份恢复/并发压测尚未验证 |

规则测试包括：严格多数、第五次否决、特殊角色视野、派西维尔候选排序、7–10人第四任务双失败、好人禁失败牌、任务结果匿名、三胜后刺杀与三败终局、非法动作不修改状态、同请求不能改票。

接口测试包括：会话鉴权、非成员拒绝、座位不能伪造、真人席未满不能开局、密票期间他人视图完全不变、重复请求、WS重连与认证、断开时连接计数释放、真实持久化恢复、截止时间、邀请码、未配置模型拒绝、请求大小、会话撤销。

`.github/workflows/ci.yml` 已提供Python测试、安装手机依赖、完整tsc/Jest、Expo依赖检查及Android/iOS JS bundle导出。源码CI已于2026-09-23通过：[run 35841427887](https://github.com/zzjw0611/AvalonGame/actions/runs/35841427887)，源码commit `814acadff7d4c68dcb3472b7a5ae3b5c9f37cbf3`。初次CI发现Jest类型显式导入和Expo版本匹配问题，已修正并再次验证；bundle导出仍不等于原生编译。Maestro真机冒烟脚本在 `mobile/.maestro/smoke.yaml`，本次未运行。

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

## Android 原生内测构建

独立工作流：[run 35840675433](https://github.com/zzjw0611/AvalonGame/actions/runs/35840675433)。工作流先验证手机代码，再`expo prebuild`，最后Gradle `assembleRelease`，仅ARM64架构。使用模板公开测试签名；不代表正式签名、商店审核或真机对局已通过。详细状态以该工作流结果为准，不凭配置文件宣称产物已经存在。
