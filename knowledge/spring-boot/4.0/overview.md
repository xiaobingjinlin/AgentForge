# Spring Boot 4.0 分层架构总览

AgentForge 默认采用经典四层结构：

```
Controller → Service → Mapper → Entity
```

## 生成顺序

1. **Entity**：定义数据模型与持久化映射。
2. **Mapper**：定义数据访问接口与 SQL。
3. **Service**：封装业务逻辑与事务。
4. **Controller**：暴露 REST API。
5. **Config**：数据源、MyBatis、环境配置。

## 包路径约定

- 基础包：`com.example.demo`
- 子包：`entity`、`mapper`、`service`、`controller`、`config`

## 技术栈版本

- JDK 21
- Spring Boot 4.0.7
- Maven 构建，`pom.xml` 继承 `spring-boot-starter-parent`

## 代码风格

- 优先构造器注入（配合 Lombok `@RequiredArgsConstructor` 可选）。
- REST 路径统一前缀 `/api/`。
- 类名与文件名一致，一个 public 类一个文件。
