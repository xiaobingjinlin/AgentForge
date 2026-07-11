# Spring Boot 能力层模板（Phase 1）

类比 Docker：**base = 基础镜像**，**capabilities = 可叠加能力层**，**项目 template_stack = 运行镜像组成**。

## 目录结构

```
templates/spring-boot/4.0/
├── base/                    # 最小可运行 Web 工程
└── capabilities/
    └── springdoc/
        ├── manifest.json    # 能力契约（依赖、配置、验证命令）
        └── overlay/         # 相对 base 的增量文件
```

## manifest.json 字段

| 字段 | 说明 |
|------|------|
| `id` | 能力标识，如 `springdoc` |
| `requires` | 依赖层，默认 `["base"]` |
| `pom.dependencies` | 合并进 `pom.xml` 的 Maven 依赖 |
| `application_yml` | 追加到 `application.yml` 的配置片段 |
| `verify.command` | 验证命令，默认 `mvn -q -DskipTests compile` |

## 项目能力栈

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

## 验证

```bash
.venv/bin/python scripts/verify_capabilities.py
```

## 新增能力层（如 mybatis）

1. 创建 `capabilities/mybatis/manifest.json` + `overlay/`
2. 确保 `mvn compile` 可通过
3. 运行 `verify_capabilities.py` 并补充专项用例

对话生成代码时，沙盒会按项目的 `template_stack` 组合模板（含已启用能力）。

## Phase 2：对话自动叠加

在聊天中直接说即可，无需手动调 API：

- `给项目加上 springdoc`
- `启用 Swagger 接口文档`
- `加 springdoc 并生成 Order 模块 CRUD`（先叠加能力，再生成业务代码）

验证：

```bash
.venv/bin/python scripts/verify_capability_conversation.py
```

新增能力的对话关键词：在 `manifest.json` 的 `keywords` 数组中声明。

## Phase 3：LLM 造层

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

## 生态策略：拒绝非 Spring Boot 能力

对话或 API 请求叠加能力时，若技术不属于 **Spring Boot 后端生态**（如 React、Vue、Django、Go），将直接拒绝，不造层、不修改 `template_stack`。

- 已入库能力（`capabilities/`、`_generated/`）一律放行
- 允许列表：`redis`、`mybatis`、`kafka`、`jwt` 等常见 Spring Boot 集成
- 拒绝列表：`react`、`vue`、`django`、`flutter` 等

验证：

```bash
.venv/bin/python scripts/verify_capability_policy.py
```

手动造层 API：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/{project_id}/capabilities/redis/generate \
  -H "Content-Type: application/json" \
  -d '{"message": "集成 Redis 缓存", "verify": false}'
```
