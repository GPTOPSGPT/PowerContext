# Evidence Desk 验证记录

记录日期：2026-11-07。以下只记录已实际执行的结果；站点发布和 Qoder UID 尚待核对。

## Qoder 开发

- `qodercli` 版本：1.1.83，已登录的个人账号。
- Qoder 阅读 `BRIEF.md` 后生成 Flask 应用、SQL、模板、样例数据、33 个测试和 README。
- 首次运行测试为 32 通过、1 失败。将准确失败项 `TestReportRoute.test_report_no_ids` 交回 Qoder；Qoder 修正空状态提示文案。
- Qoder 再根据真实 seekdb 的 `Unknown collation: 'utf8mb4_unicode_ci'` 修正 `init.sql` 和 `db.py` 为 seekdb 支持的 `utf8mb4_bin`。
- Qoder 生成代码后，Codex 仅修正 `config.py` 的空密码开发环境兼容，并执行验证。

## 本地自动化测试

命令（在 `qoder/` 执行）：

```bash
/private/tmp/qoder-evidence-venv/bin/python -m pytest tests -q
```

退出码 0；结果：`33 passed in 1.09s`。此虚拟环境为本机临时测试环境，按 `requirements.txt` 可重建。

## 真实 seekdb 查询

连接：通过 SSH 临时端口转发访问 trip ECS 上既有 seekdb 服务；仅创建此前不存在的 `evidence_desk` 独立数据库。未改动其他数据库。执行 `init.sql`、`sample_data.sql` 后，`SELECT COUNT(*) FROM evidence_desk.records` 返回 12。

在同一数据库上以 Flask 测试客户端实际请求：

```text
GET /api/search?q=认证&date_from=2026-10-01&date_to=2026-11-30
HTTP 200; search_count: 1
first_source: git:commit:a3f8c21 / src/auth/jwt.py
GET /report?ids=1,3
HTTP 200; report_sources_present: True
```

这些结果来自 seekdb 中的样例记录查询，周报页面包含对应来源。样例数据是演示用虚构记录，不代表真实用户使用或提效统计。

## 尚未完成

- Qoder Sites 公开站点 URL、无痕访问验证。
- Qoder 账号 UID 与开发会话截图或录屏。
- 平台提交。
