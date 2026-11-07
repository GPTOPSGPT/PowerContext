# Evidence Desk — 团队工作记录管理与周报生成工具

> 解决团队周报与科研记录散落、证据难找的问题。导入带来源与日期的工作记录，按关键词和日期查找，选中记录后生成带精确来源的周报草稿。核心存储使用 seekdb（MySQL 协议）。

## 目录

- [功能概览](#功能概览)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [数据库初始化](#数据库初始化)
- [启动应用](#启动应用)
- [使用流程](#使用流程)
- [API 接口](#api-接口)
- [运行测试](#运行测试)
- [项目结构](#项目结构)
- [安全说明](#安全说明)
- [开发证据](#开发证据)

## 功能概览

| 功能 | 说明 |
|------|------|
| 导入记录 | JSON 批量导入，支持单条或数组，自动校验字段 |
| 搜索记录 | 关键词搜索（标题/内容/标签）+ 日期范围过滤，由 seekdb SQL 执行 |
| 查看来源 | 每条记录显示精确来源（文件路径、commit hash、文档链接等） |
| 生成周报 | 勾选多条记录 → 按标签分组 → 输出 Markdown 周报草稿，含所有来源和记录 ID |
| REST API | `/api/search` 提供 JSON 搜索接口 |

## 技术栈

- Python 3.11+
- Flask 3.x
- PyMySQL（连接 seekdb / MySQL 协议数据库）
- Jinja2 模板
- pytest 自动化测试

## 快速开始

```bash
# 1. 进入项目目录
cd qoder

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置数据库连接
cp .env.example .env
# 编辑 .env，填入 seekdb 连接信息

# 4. 初始化数据库
mysql -h $SEEKDB_HOST -P $SEEKDB_PORT -u $SEEKDB_USER -p$SEEKDB_PASSWORD < init.sql

# 5. 导入样例数据（可选）
mysql -h $SEEKDB_HOST -P $SEEKDB_PORT -u $SEEKDB_USER -p$SEEKDB_PASSWORD evidence_desk < sample_data.sql

# 6. 启动应用
python app.py
# 访问 http://127.0.0.1:5100
```

## 数据库初始化

### 表结构

```sql
CREATE TABLE records (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    title       VARCHAR(500) NOT NULL,   -- 记录标题
    content     TEXT NOT NULL,           -- 正文内容
    source      VARCHAR(1000) NOT NULL,  -- 来源（文件路径、URL、系统名等）
    record_date DATE NOT NULL,           -- 记录日期
    tags        VARCHAR(1000) DEFAULT '',-- 标签，逗号分隔
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

### 使用 init.sql

```bash
# 创建数据库和表（seekdb 默认端口 2881）
mysql -h 127.0.0.1 -P 2881 -u evidence_desk -p < init.sql
```

> 排序规则说明：seekdb 仅支持 `utf8mb4_general_ci` 和 `utf8mb4_bin`，不支持 `utf8mb4_unicode_ci`。本项目统一使用 `utf8mb4_bin`。可用以下语句确认：
>
> ```sql
> SHOW COLLATION LIKE 'utf8mb4%';
> ```

### 导入样例数据

`sample_data.sql` 包含 12 条真实风格的工作记录，覆盖后端、前端、运维、会议、调研等场景：

```bash
mysql -h 127.0.0.1 -P 2881 -u evidence_desk -p evidence_desk < sample_data.sql
```

## 启动应用

```bash
# 确保 .env 已配置
python app.py
```

应用默认监听 `http://127.0.0.1:5100`。

**如果没有配置 seekdb 连接**，首页会显示明确的错误提示："缺少必要的环境变量" 或 "无法连接到 seekdb 数据库"，不会用假数据冒充。

## 使用流程

### 1. 导入数据

访问 `/import`，粘贴 JSON：

```json
[
  {
    "title": "完成用户认证模块重构",
    "content": "将 session-based 认证迁移到 JWT token 方案...",
    "source": "git:commit:a3f8c21 / src/auth/jwt.py",
    "record_date": "2026-10-27",
    "tags": "后端,认证,重构"
  }
]
```

也可以通过 Web 界面或直接执行 SQL 导入。

### 2. 搜索记录

访问 `/search`，支持：
- **关键词搜索**：匹配标题、正文、标签
- **日期范围**：起始日期 + 结束日期
- 组合使用

示例查询 URL：
```
/search?q=认证&date_from=2026-10-01&date_to=2026-10-31
```

搜索结果展示每条记录的标题、日期、ID、内容摘要、来源和标签。

### 3. 查看记录详情与来源

点击任意记录标题进入详情页 `/record/<id>`，显示完整正文和精确来源。

### 4. 生成周报草稿

在搜索结果页勾选需要的记录，点击「生成周报草稿」按钮。系统会：
1. 按标签自动分组
2. 生成 Markdown 格式周报，包含日期范围、工作内容摘要
3. 列出所有涉及的记录 ID 和来源汇总

## API 接口

### GET /api/search

```
GET /api/search?q=关键词&date_from=2026-10-01&date_to=2026-10-31
```

响应：
```json
{
  "records": [...],
  "count": 5
}
```

## 运行测试

```bash
cd qoder
python -m pytest tests/ -v
```

测试包含：
- **验证逻辑单元测试**：输入校验、日期解析、边界条件（18 个用例）
- **Flask 路由测试**：使用 mock DB 测试所有页面和 API（12 个用例）
- **周报生成测试**：空数据、单条、多条多标签场景（3 个用例）

总计 **33 个测试用例**，无需真实数据库即可运行。

### 预期输出

```
tests/test_app.py::TestValidateRecord::test_valid_record PASSED
tests/test_app.py::TestValidateRecord::test_missing_title PASSED
...
tests/test_app.py::TestDraftGeneration::test_generate_draft_multiple_tags PASSED
========================= 33 passed in X.XXs =========================
```

## 项目结构

```
qoder/
├── BRIEF.md            # 竞赛需求简报
├── README.md           # 本文件
├── .env.example        # 环境变量模板（不含敏感信息）
├── requirements.txt    # Python 依赖
├── config.py           # 数据库配置（从环境变量读取）
├── validation.py       # 输入验证与清洗
├── db.py               # 数据库操作层（PyMySQL，全部参数化查询）
├── app.py              # Flask 主应用
├── init.sql            # 数据库建表脚本
├── sample_data.sql     # 12 条样例工作记录
├── templates/
│   ├── base.html       # 基础布局模板
│   ├── index.html      # 首页
│   ├── import.html     # 导入页面
│   ├── search.html     # 搜索页面（含勾选功能）
│   ├── record_detail.html  # 记录详情页
│   └── report.html     # 周报草稿页
├── static/             # 静态资源目录
└── tests/
    ├── __init__.py
    └── test_app.py     # 自动化测试（33 个用例）
```

## 安全说明

- 所有 SQL 查询使用 `%s` 参数化，防止注入
- 输入长度限制：标题 500、正文 100000、来源 1000、标签 1000、关键词 200
- 日期格式严格校验（YYYY-MM-DD）
- `.env.example` 不包含任何密码或令牌
- 不依赖付费模型或外部 API

## 开发证据

本项目由 Qoder 会话实际开发，以下为真实开发过程记录：

### 需求拆解

Qoder 阅读 `BRIEF.md` 后，将需求拆解为 7 个任务：
1. 项目结构与配置（config.py, .env.example, requirements.txt）
2. SQL 模式与样例数据（init.sql, sample_data.sql）
3. Flask 应用核心（app.py, db.py, validation.py）
4. HTML 模板（6 个 Jinja2 模板）
5. 自动化测试（33 个 pytest 用例）
6. 中文 README
7. 测试执行与验证

### 关键技术决策

- **seekdb 作为唯一数据源**：没有 seekdb 时明确报错，不使用内存假数据
- **全参数化 SQL**：db.py 中所有查询使用 `%s` 占位符
- **Mock 测试策略**：单元测试和路由测试使用 MockConnection/MockCursor，无需真实数据库
- **周报按标签分组**：自动生成结构化 Markdown，保留来源追溯

### Qoder UID

Qoder 账号 UID：待从 Qoder 个人资料页核对后填写。CLI 显示的用户名不是 UID。

### 文件清单

主要应用代码由 Qoder 会话生成；后续根据真实 seekdb 验证，Codex 对 `config.py` 做了一处空密码兼容修复。真实测试结果见 [EVIDENCE.md](EVIDENCE.md)。

| 文件 | 行数 | 用途 |
|------|------|------|
| config.py | 25 | 环境变量配置加载 |
| validation.py | 72 | 输入验证与清洗 |
| db.py | 95 | 数据库操作层 |
| app.py | 155 | Flask 主应用 |
| init.sql | 20 | 建表脚本 |
| sample_data.sql | 28 | 12 条样例数据 |
| templates/*.html | ~280 | 6 个页面模板 |
| tests/test_app.py | 230 | 33 个自动化测试 |
| README.md | 本文件 | 中文文档 |
