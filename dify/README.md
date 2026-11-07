# 记仇 NPC（Dify × seekdb）

一个玩家用一句话捉弄 NPC。再次输入同一玩家名时，NPC 会从 seekdb 读出上一回合的恶作剧并回嘴，同时保存本次互动。Dify 负责输入、HTTP 调用与结果输出；seekdb 实际保存并查询跨回合记忆。无模型和插件依赖。

## 材料与状态

- `app.yml`：Dify Workflow DSL，先部署后端再导入。
- `schema.sql`：seekdb 初始化表。
- `npc_backend.py`：Dify HTTP 节点到 seekdb 的桥接服务。
- `requirements.txt`：Python 依赖。

**当前状态：DSL 已编写但尚未在 Dify 实例中导入和实跑；不能将其当作已验收作品。** 需在目标 Dify 版本导入、将 HTTP 节点 URL 改成 Dify 可访问的后端地址，并记录真实的两轮运行及 seekdb 查询结果。

## 初始化与运行

1. 部署 seekdb，执行 `mysql -h HOST -P PORT -u USER -p < schema.sql`。
2. `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`。
3. 配置 `SEEKDB_HOST`、`SEEKDB_PORT`、`SEEKDB_USER`、`SEEKDB_PASSWORD`。密码只放运行环境，不写入 DSL 或仓库。执行 `python npc_backend.py`。
4. 从 Dify Studio 导入 `app.yml`。在 HTTP 节点将 `http://npc-backend:8765/turn` 换成 Dify 容器或云端可访问的地址；若用云端 Dify，必须用受控 HTTPS 地址。发布应用并运行。

## 验证样例

先执行 `TRUNCATE TABLE dify_prank_npc.prank_turns;` 重置。

1. 玩家名 `demo-01`，恶作剧 `把闹钟藏进冰箱`。预期 `previous_prank` 为 `null`。
2. 仍用 `demo-01`，恶作剧 `把键盘换成香蕉`。预期 `previous_prank` 为 `把闹钟藏进冰箱`，回应引用第一次的恶作剧。
3. seekdb 执行 `SELECT id, player, prank, reaction FROM dify_prank_npc.prank_turns WHERE player='demo-01' ORDER BY id;`，应有两行。第二回合读取的内容来自第一行，而非 Dify 会话内变量。

待补：实际 Dify 导入截图/运行日志、真实 SQL 查询结果、适用 Dify 与 seekdb 精确版本、后端服务部署配置。平台评测前必须补齐。
