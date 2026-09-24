# 上游搜索与改造记录

核对时间：2026-09-23。使用 GitHub 仓库搜索与文件读取；没有把 README 宣传当作压测结果。

| 项目 | 适配判断 | 本项目使用范围 |
|---|---|---|
| [xqbjs/AvalonGame](https://github.com/xqbjs/AvalonGame) | 最接近真人 + LLM、FastAPI 与实时房间；Apache-2.0 | 人数配置与阶段机制的选择性改造，重写服务与原生 UI |
| [jonathanmli/Avalon-LLM](https://github.com/jonathanmli/Avalon-LLM) | 研究与策略参考；README benchmark 配置限五人，许可未明确确认 | 未复制代码 |
| [vck3000/ProAvalon](https://github.com/vck3000/ProAvalon) | 真人在线平台、Node/Socket.io；不是原生 App/现成 LLM 适配 | 未复制代码 |

选定上游 commit：`c46f1d923930484ede6dbf0d44e6f3e3889b0afa`。
实际引擎路径是 `games/games/avalon/engine.py`，README 的简写路径并非仓库根目录实际路径。
源文件 blob：`e768ac04226684f5c5a3ec8e5fa2e94e9288c358`。

## 具体差异

- `AvalonBasicConfig.QUEST_PRESET`：保留 5–10 人的阵营比例、任务人数和失败门槛，移入 `backend/app/rules.py`。
- `from_num_players`：上游 `kwargs.update(role_flags)` 会覆盖用户角色选择；改为验证自选角色与阵营容量。
- `gather_team_votes`：上游第五提案自动通过；改为严格多数，连续第五次否决立即判邪恶胜。
- `get_partial_sides`：上游这个函数给梅林或邪恶返回完整阵营向量；改为按角色裁剪的座位集合，处理莫德雷德和奥伯伦例外。
- 刺杀：不从真实好人中筛选菜单；任何其他座位可选，后台仅一次判定是否梅林。
- 密票：移除“整张真实局面交给玩家”的接口模式；每席请求绑定游戏/阶段/座位，收齐前不公开他人提交状态或值。
- 存储与通信：新建持久化移动 API、独立视角 WS、幂等操作、重连补偿；未搬入训练框架、模型权重或网页客户端。

这里指出的是读取到的特定引擎函数行为，不代表已经审计完上游所有调用路径，也不宣称其全部运行模式都会暴露该问题。

## 许可

上游根目录 LICENSE.txt 为 Apache License 2.0；保留完整许可和 README 中署名 MinkunXue / FaLi，在改造代码标明变更。未复制上游图片、数据集、配置密钥、未明确授权研究仓库代码。

## 手机依赖核对

对照 Expo 官方 `sdk-56` 分支 `templates/expo-template-default/package.json` 和 `packages/expo/bundledNativeModules.json`，使用 Expo 56.0.22 / React Native 0.85.3 / React 19.2.3 配套版本。官方 main 当时含预览版，未采用。没有声称 SDK56 是最新 SDK。

资料：[官方 SDK56 模板](https://github.com/expo/expo/blob/sdk-56/templates/expo-template-default/package.json)、[原生模块配套表](https://github.com/expo/expo/blob/sdk-56/packages/expo/bundledNativeModules.json)。
