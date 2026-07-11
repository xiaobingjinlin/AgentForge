# Spring Boot 4.0 配置层指南

## application.yml

- 主配置位于 `src/main/resources/application.yml`。
- 常用配置段：`server.port`、`spring.datasource`、`mybatis.mapper-locations`。

```yaml
server:
  port: 8080

spring:
  application:
    name: demo
  datasource:
    url: jdbc:postgresql://localhost:5432/demo
    username: ${DB_USER:postgres}
    password: ${DB_PASSWORD:postgres}
    driver-class-name: org.postgresql.Driver

mybatis:
  mapper-locations: classpath:mapper/*.xml
  configuration:
    map-underscore-to-camel-case: true
```

## Java 配置类

- 放在 `com.example.demo.config` 包，类名以 `Config` 结尾。
- 使用 `@Configuration`，Bean 方法加 `@Bean`。

```java
@Configuration
public class MyBatisConfig {
    // 如需自定义 SqlSessionFactory 在此声明
}
```

## 环境隔离

- `application-dev.yml` / `application-prod.yml` 通过 `spring.profiles.active` 切换。
- 敏感信息使用环境变量占位符 `${VAR_NAME}`。

## 与 Web 层协作

- CORS 需求可定义 `WebMvcConfigurer` Bean。
- 全局异常处理使用 `@RestControllerAdvice`。

## Spring Boot 4.0 依赖

- 父 POM：`spring-boot-starter-parent` 4.0.x
- Web：`spring-boot-starter-web`
- 校验：`spring-boot-starter-validation`
