# AgentForge

基于 LangGraph 的多智能体 Spring Boot 代码生成平台：对话叠加能力层 → 路由领域 SubGraph → 三阶段 codegen → 沙盒落盘。

## 仓库结构

```
AgentForge/
├── agentforge/          # Python 后端（FastAPI + LangGraph）
├── frontend/            # Vue 3 对话界面
├── templates/           # Spring Boot 只读模板（base + capabilities）
├── knowledge/           # RAG 知识库语料
├── scripts/             # 启停与验证脚本
├── sql/                 # PostgreSQL / pgvector 初始化
├── sandbox/             # 运行时沙盒（git 忽略内容，保留 README）
└── document/            # 使用文档
```

后端包结构详见 [agentforge/README.md](./agentforge/README.md)。

## 快速开始

### 环境要求

- Python ≥ 3.12
- Node.js（前端）
- PostgreSQL（`agentforge` 向量库 + `agentforge_meta` 元数据库）
- Redis（可选缓存）
- Qwen API（`QWEN_API_KEY`、`QWEN_BASE_URL`）

环境变量与启停命令见 [document/服务启停.md](./document/服务启停.md)。

### 安装与启动

```bash
# 后端依赖
python -m venv .venv
.venv/bin/pip install -e .

# 首次部署：建库 + 初始化表结构（需 PostgreSQL + pgvector）
.venv/bin/python scripts/init_databases.py

# 前端依赖
cd frontend && npm install && cd ..

# 启动（两个终端）
bash scripts/run_api.sh
cd frontend && npm run dev
```

- API 文档：http://127.0.0.1:8000/docs
- 前端：http://127.0.0.1:5173

多轮对话场景示例见 [document/对话编程场景示例.md](./document/对话编程场景示例.md)。

---

## Spring Boot 能力层（Phase 1–3）

类比 Docker：**base = 基础镜像**，**capabilities = 可叠加能力层**，**项目 template_stack = 运行镜像组成**。

详细说明亦见：[templates/spring-boot/4.0/capabilities/README.md](./templates/spring-boot/4.0/capabilities/README.md)

### 目录结构

```
templates/spring-boot/4.0/
├── base/                    # 最小可运行 Web 工程
└── capabilities/
    └── springdoc/
        ├── manifest.json    # 能力契约（依赖、配置、验证命令）
        └── overlay/         # 相对 base 的增量文件
```

### manifest.json 字段

| 字段 | 说明 |
|------|------|
| `id` | 能力标识，如 `springdoc` |
| `requires` | 依赖层，默认 `["base"]` |
| `pom.dependencies` | 合并进 `pom.xml` 的 Maven 依赖 |
| `application_yml` | 追加到 `application.yml` 的配置片段 |
| `verify.command` | 验证命令，默认 `mvn -q -DskipTests compile` |

### 项目能力栈

创建项目时 `metadata.template_stack` 默认为 `["base"]`。

启用 springdoc：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/{project_id}/capabilities/springdoc \
  -H "Content-Type: application/json" \
  -d '{"verify": false}'
```

查看可用能力：

```bash
curl http://127.0.0.1:8000/api/projects/{project_id}/capabilities
```

### Phase 2：对话自动叠加

在聊天中直接说即可，无需手动调 API：

- `给项目加上 springdoc`
- `启用 Swagger 接口文档`
- `加 springdoc 并生成 Order 模块 CRUD`（先叠加能力，再生成业务代码）

验证：

```bash
.venv/bin/python scripts/verify_capability_conversation.py
```

新增能力的对话关键词：在 `manifest.json` 的 `keywords` 数组中声明。

### Phase 3：LLM 造层

当 Registry（含 `_generated/`）中**没有**匹配能力时，对话会自动：

1. 推断缺失能力（如 `redis`、`mybatis`）
2. 调用 LLM 生成 `manifest.json` + `overlay/`
3. 沙盒验证（`mvn compile`，无 mvn 时降级为结构校验）
4. 晋升到 `capabilities/_generated/{id}/` 供后续复用

示例对话：

```
给项目加上 redis 缓存
```

验证（fixture，无需 LLM API）：

```bash
.venv/bin/python scripts/verify_capability_generator.py
```

手动造层 API：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/{project_id}/capabilities/redis/generate \
  -H "Content-Type: application/json" \
  -d '{"message": "集成 Redis 缓存", "verify": false}'
```

### 生态策略：拒绝非 Spring Boot 能力

对话或 API 请求叠加能力时，若技术不属于 **Spring Boot 后端生态**（如 React、Vue、Django、Go），将直接拒绝，不造层、不修改 `template_stack`。

- 已入库能力（`capabilities/`、`_generated/`）一律放行
- 允许列表：`redis`、`mybatis`、`kafka`、`jwt` 等常见 Spring Boot 集成
- 拒绝列表：`react`、`vue`、`django`、`flutter` 等

验证：

```bash
.venv/bin/python scripts/verify_capability_policy.py
```

### 能力层验证脚本汇总

```bash
.venv/bin/python scripts/verify_capabilities.py
.venv/bin/python scripts/verify_capability_conversation.py
.venv/bin/python scripts/verify_capability_generator.py
.venv/bin/python scripts/verify_capability_policy.py
```

---

## `.gitignore` 说明

本仓库**已包含**根目录 [`.gitignore`](./.gitignore)。若你 fork、解压或从其他渠道获取代码时**根目录没有 `.gitignore`，请自行添加**，至少排除以下内容，避免密钥与运行时产物进入版本库：

| 类别 | 建议忽略 |
|------|----------|
| 环境与密钥 | `.env`、`.env.*` |
| Python | `.venv/`、`__pycache__/`、`*.pyc`、测试缓存 |
| 前端 | `node_modules/`、`frontend/dist/` |
| IDE | `.idea/`、`.vscode/` |
| 运行时 | `logs/`、`sandbox/*`（可保留 `sandbox/README.md`） |
| LLM 造层产出 | `templates/**/capabilities/_generated/*`（可保留 `.gitkeep`） |
| 系统文件 | `.DS_Store` |

本地私有文档（按需加入 `.gitignore`，本仓库已配置）：

- `document/本地提供.md`
- `document/项目清单.md`
- `document/项目职责-需求说明.md`

**切勿提交**：API Key、数据库密码、`.env` 文件及 `sandbox/` 下生成的工程代码。

---

## 相关文档

- [document/服务启停.md](./document/服务启停.md) — 启停命令与环境变量
- [document/对话编程场景示例.md](./document/对话编程场景示例.md) — Order 模块多轮对话演示
- [templates/spring-boot/4.0/capabilities/README.md](./templates/spring-boot/4.0/capabilities/README.md) — 能力层机制原文
