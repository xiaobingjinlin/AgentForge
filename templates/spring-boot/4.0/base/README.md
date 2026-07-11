# Spring Boot 4.0 模板（JDK 21）

AgentForge 默认 Java 后端模板，用于代码生成落盘与编译验证。

## 技术栈

| 项 | 版本 |
|----|------|
| JDK | 21 |
| Spring Boot | 4.0.7 |
| 构建工具 | Maven |
| 虚拟线程 | 已开启 |

## 目录结构

```
base/
├── pom.xml
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    ├── controller/    # REST 接口
    ├── service/       # 业务逻辑
    ├── mapper/        # 数据访问
    ├── entity/        # 实体类
    └── config/        # 配置类
```

## 本地运行

```bash
cd templates/spring-boot/4.0/base
mvn spring-boot:run
```

验证：http://localhost:8080/api/health

## 与 AgentForge 集成

- 模板路径：`templates/spring-boot/4.0/base/`
- 落盘沙盒：`sandbox/{project_id}/`（由 LangChain 沙盒工具读写）
- 创建项目时可从模板复制到沙盒目录
