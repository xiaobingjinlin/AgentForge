# Spring Boot 2.7 分层架构（版本快照）

Spring Boot 2.7 是 2.x 末代 LTS，仍广泛使用 `javax.*` 命名空间。

## 关键差异（相对 3.x/4.x）

- 父 POM：`spring-boot-starter-parent` 2.7.x
- JDK 8 / 11 / 17
- 校验：`javax.validation.constraints.*`
- Servlet API：`javax.servlet.*`

## 分层结构

Controller → Service → Mapper/Repository → Entity

## 依赖示例

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.18</version>
</parent>
```

## REST 风格

与 3.x 相同：@RestController + @RequestMapping，JSON 响应，路径前缀 `/api/`。
