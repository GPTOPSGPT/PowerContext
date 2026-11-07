-- Evidence Desk 样例数据
USE evidence_desk;

INSERT INTO records (title, content, source, record_date, tags) VALUES
('完成用户认证模块重构', '将原有的 session-based 认证迁移到 JWT token 方案，支持 refresh token 自动续期。修改了 auth middleware 和 login/logout API，所有单元测试已通过。', 'git:commit:a3f8c21 / src/auth/jwt.py', '2026-10-27', '后端,认证,重构'),
('修复订单列表分页错误', '生产环境反馈第3页之后数据重复，排查发现 OFFSET 计算未考虑已删除记录的软删除过滤。修复后在 staging 验证通过。', 'jira:ORD-1482 / src/api/orders.py:L142', '2026-10-28', '后端,Bug修复,订单'),
('参加架构评审会议', '讨论了 Q4 微服务拆分计划，决定先将消息队列从 RabbitMQ 迁移到 Kafka。会后整理了会议纪要并同步给相关团队。', '飞书文档:docs/architecture/q4-migration-plan', '2026-10-28', '会议,架构,消息队列'),
('编写数据导出功能测试用例', '为 CSV/Excel 导出功能补充了 23 个边界条件测试，覆盖空数据集、超大文件、特殊字符编码等场景。覆盖率从 67% 提升到 89%。', 'git:commit:b7e2d45 / tests/test_export.py', '2026-10-29', '测试,数据导出,质量'),
('调研日志聚合方案', '对比了 ELK、Loki+Grafana、ClickHouse 三种方案的成本和运维复杂度。初步结论：当前规模下 Loki 性价比最高，已输出对比报告。', 'confluence:tech-research/log-aggregation-2026q4', '2026-10-30', '调研,日志,基础设施'),
('优化首页加载性能', '通过懒加载图表组件和预取关键接口，首页 LCP 从 3.2s 降至 1.8s。使用 Lighthouse 进行了前后对比测试。', 'git:commit:c9a1f33 / src/pages/dashboard.tsx', '2026-10-30', '前端,性能优化,用户体验'),
('更新 API 文档至 OpenAPI 3.1', '将所有 REST API 端点的文档从 Swagger 2.0 升级到 OpenAPI 3.1 规范，补充了 request/response schema 示例。', 'git:commit:d4b5e67 / docs/openapi.yaml', '2026-10-31', '文档,API,规范化'),
('处理客户紧急工单 #8832', '客户反馈批量导入失败，定位为 Excel 解析库版本兼容问题。临时回退依赖版本并推送热修复，后续安排升级 xlsx 库。', 'zendesk:#8832 / src/services/import/excel_parser.py', '2026-11-01', '运维,客户支持,紧急'),
('完成代码审查：支付回调安全加固', 'Review 了同事提交的支付回调验签逻辑 PR，建议增加幂等性检查和异常告警。PR 已合并。', 'github:PR#456 / src/payment/callback.py', '2026-11-02', '代码审查,安全,支付'),
('部署监控告警规则', '在 Prometheus 中新增了 5 条告警规则，覆盖 P99 延迟、错误率、队列积压等核心指标。已在 Grafana 配置对应面板。', 'grafana:dashboard/prod-alerts / prometheus/rules/app.yml', '2026-11-03', '运维,监控,告警'),
('撰写技术方案：多租户数据隔离', '完成了基于 Schema 级别的多租户隔离技术方案初稿，包含数据路由、迁移策略和性能影响评估。待架构组评审。', 'confluence:tech-design/multi-tenancy-schema-isolation', '2026-11-04', '架构,多租户,技术方案'),
('修复移动端表格横向滚动失效', 'iOS Safari 下 overflow-x:auto 不生效，改用 -webkit-overflow-scrolling:touch 配合容器约束解决。已在真机验证。', 'git:commit:e8f3a12 / src/styles/mobile-table.css', '2026-11-05', '前端,Bug修复,移动端');
