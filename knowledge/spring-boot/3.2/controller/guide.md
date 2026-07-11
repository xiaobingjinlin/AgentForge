# Spring Boot 3.2 Controller 层指南

## 基本结构

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public Order detail(@PathVariable Long id) {
        return orderService.getById(id);
    }
}
```

## 注解包名

- `org.springframework.web.bind.annotation.*`
- `jakarta.validation.Valid`

## CRUD 端点

- `GET /api/orders` — 列表
- `POST /api/orders` — 创建（201）
- `PUT /api/orders/{id}` — 更新
- `DELETE /api/orders/{id}` — 删除（204）
