# Spring Boot 3.2 分层架构（版本快照）

Spring Boot 3.x 基于 **Jakarta EE 9+**，包名使用 `jakarta.*` 而非 `javax.*`。

## 与 4.0 的差异要点

- 父 POM：`spring-boot-starter-parent` 3.2.x
- JDK 17+（推荐 17 或 21）
- `@RestController`、`@Service`、`@Mapper` 用法与 4.0 基本一致
- 校验注解：`jakarta.validation.constraints.*`

## 生成顺序

Entity → Mapper → Service → Controller → Config

## REST 约定

- 路径前缀 `/api/`
- 创建成功返回 HTTP 201
- 使用 `ResponseEntity` 表达状态码
