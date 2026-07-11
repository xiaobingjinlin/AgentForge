# Spring Boot 4.0 Controller 层（REST API）指南

## 基本结构

- 类放在 `com.example.demo.controller` 包。
- 使用 `@RestController` + `@RequestMapping("/api/orders")` 定义资源路径。
- 通过构造器注入对应 `Service`。

## CRUD 端点约定

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders` | 列表 |
| GET | `/api/orders/{id}` | 详情 |
| POST | `/api/orders` | 创建 |
| PUT | `/api/orders/{id}` | 更新 |
| DELETE | `/api/orders/{id}` | 删除 |

## 示例代码

```java
@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {
    private final OrderService orderService;

    @GetMapping
    public List<Order> list() {
        return orderService.listAll();
    }

    @GetMapping("/{id}")
    public Order detail(@PathVariable Long id) {
        return orderService.getById(id);
    }

    @PostMapping
    public ResponseEntity<Order> create(@Valid @RequestBody Order order) {
        Order created = orderService.create(order);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

## 响应规范

- 成功创建返回 `201 Created`；删除成功可返回 `204 No Content`。
- 统一使用 JSON；日期字段遵循 ISO-8601。
- 路径变量与请求体字段校验使用 `@Valid` + Bean Validation 注解。

## 与 Spring Boot 4.0 兼容

- 使用 `jakarta.validation.*` 而非 `javax.validation`。
- 健康检查可参考模板 `HealthController`：`GET /api/health` 返回 `{"status":"ok"}`。
