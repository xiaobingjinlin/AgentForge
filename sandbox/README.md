# AgentForge 沙盒目录

每个 `project_id` 对应一个独立子目录，Agent 的文件读写与命令执行限制在各自沙盒内。

```
sandbox/
  {project_id}/          # 运行时生成，不提交 Git
    src/...
    pom.xml
```

环境变量：
- `SANDBOX_ROOT` — 沙盒根目录，默认项目根目录下的 `sandbox/`
