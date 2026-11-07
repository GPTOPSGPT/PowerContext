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
3. 配置 `SEEKDB_HOST`、`SEEKDB_PORT`、`SEEKDB_USER`、`SEEKDB_PASSWORD` 和随机生成的 `NPC_API_TOKEN`。密码和令牌只放运行环境，不写入 DSL 或仓库。执行 `python npc_backend.py`。
4. 从 Dify Studio 导入 `app.yml`。HTTP 节点默认目标是受控 HTTPS 地址 `https://tianyuai.net/contest/dify-npc/turn`；若改用其他部署，更换此 URL。在 HTTP 节点将 `REPLACE_WITH_TOKEN` 更新为与后端一致的 Bearer 令牌，勿将填入真实令牌后的 DSL 导出到仓库。发布应用并运行。

## 验证样例

先执行 `TRUNCATE TABLE dify_prank_npc.prank_turns;` 重置。

1. 玩家名 `demo-01`，恶作剧 `把闹钟藏进冰箱`。预期 `previous_prank` 为 `null`。
2. 仍用 `demo-01`，恶作剧 `把键盘换成香蕉`。预期 `previous_prank` 为 `把闹钟藏进冰箱`，回应引用第一次的恶作剧。
3. seekdb 执行 `SELECT id, player, prank, reaction FROM dify_prank_npc.prank_turns WHERE player='demo-01' ORDER BY id;`，应有两行。第二回合读取的内容来自第一行，而非 Dify 会话内变量。

待补：实际 Dify 导入截图/运行日志、真实 SQL 查询结果、适用 Dify 与 seekdb 精确版本、后端服务部署配置。平台评测前必须补齐。

## trip ECS 隔离部署的待批准变更

已准备的无凭据材料：`/opt/gptops/dify-npc/{npc_backend.py,schema.sql,requirements.txt}`；独立 schema `dify_prank_npc` 已建立。**以下账户、令牌、服务和公开入口均尚未创建。**

拟执行的精确权限范围（`<RANDOM_DB_PASSWORD>` 由部署时随机生成，不进入仓库或日志）：

```sql
CREATE USER 'dify_npc'@'127.0.0.1' IDENTIFIED BY '<RANDOM_DB_PASSWORD>';
GRANT SELECT, INSERT ON dify_prank_npc.* TO 'dify_npc'@'127.0.0.1';
```

桥接进程拟由 systemd 以非特权用户运行，仅监听 `127.0.0.1:8765`，内存上限 128 MiB。私有环境文件 `/opt/gptops/dify-npc/bridge.env` 为 root 所有、权限 `0600`，只含 seekdb 专用账户密码、随机 256 位 Bearer 令牌及监听配置；不得打印或提交。Nginx 仅在 `tianyuai.net:443` 的精确路径 `/contest/dify-npc/turn` 转发至 `127.0.0.1:8765/turn`，保留 `Authorization`；应用要求正确 Bearer 令牌，其他路径不开放。拟先备份现有配置、运行 `nginx -t`，成功后才 reload，并检查原站点健康与新入口未授权返回 401。

回滚顺序：在 Dify 停用此节点；移除 Nginx 的单一路径 include 并 `nginx -t && systemctl reload nginx`；`systemctl disable --now dify-npc`；撤销 `dify_npc` 的 grant 并删除该专用账户；删除 `/opt/gptops/dify-npc/bridge.env`。如需清除样例数据，先导出需要留存的评测证据，再单独删除 `dify_prank_npc` schema。回滚不触碰其他站点、数据库或容器。
