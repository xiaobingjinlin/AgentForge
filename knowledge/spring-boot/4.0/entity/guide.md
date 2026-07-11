# Spring Boot 4.0 实体层（Entity）指南

## 基本原则

- 实体类放在 `com.example.demo.entity` 包下，类名与表名对应（如 `Order`）。
- 使用 Jakarta Persistence（`jakarta.persistence.*`）注解，Spring Boot 4.0 基于 Jakarta EE。
- 主键推荐 `Long id`，配合 `@Id` + `@GeneratedValue(strategy = GenerationType.IDENTITY)`。

## 常用注解

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String name;

    private LocalDateTime createdAt;
}
```

## 字段约定

- 时间字段使用 `LocalDateTime` / `Instant`，避免 `java.util.Date`。
- 金额使用 `BigDecimal`，状态枚举使用 Java `enum` 或字符串常量。
- 可为空字段显式标注 `@Column(nullable = true)`；必填字段 `nullable = false`。

## 与 Mapper 协作

- 实体字段命名采用驼峰，数据库列可用下划线；MyBatis 开启 `map-underscore-to-camel-case`。
- 实体不要包含 HTTP 或业务逻辑，仅承载数据结构与持久化映射。

## CRUD 模块建议字段

- `id`：主键
- 业务主字段（如 `name`、`status`）
- `createdAt` / `updatedAt`：审计字段（可选 `@PrePersist`）
