# AgentForge 后端包结构

```
agentforge/
├── api/              # FastAPI 路由、中间件、依赖注入
├── agents/           # 三层多智能体
│   ├── router.py     # 第一层：路由分发 Agent
│   ├── integrator.py # 第三层：结果整合 Agent
│   ├── codegen/      # 三阶段代码生成（骨架→实现→修复）
│   ├── subgraphs/    # 第二层：领域 SubGraph
│   ├── graph.py      # LangGraph 主图
│   └── handoff.py    # Handoff 上下文控制
├── plugins/          # 可插拔技术栈（spring-boot / 未来 python·go·vue）
├── services/         # 对话、项目上下文、落盘服务
├── core/             # 配置、日志、连接池、注册中心
├── db/               # PostgreSQL 存储
├── rag/              # RAG 入库、检索、rerank
├── cache/            # Redis
├── sandbox/          # LangChain 沙盒工具
├── templates/        # base + 能力层组合（capabilities/）
└── utils/            # LLM 等通用工具
```

扩展新语言框架：实现 `FrameworkPlugin` 并在 `plugins/__init__.py` 注册。
