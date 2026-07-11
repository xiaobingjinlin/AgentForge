# Spring Boot 4.0 Service 层指南

## 职责边界

- Service 封装业务逻辑，协调 Mapper，不直接处理 HTTP 请求/响应。
- 接口 + 实现分离：`OrderService` + `OrderServiceImpl`。
- 实现类使用 `@Service`，通过构造器注入 Mapper。

## 接口示例

```java
public interface OrderService {
    Order getById(Long id);
    List<Order> listAll();
    Order create(Order order);
    Order update(Long id, Order order);
    void delete(Long id);
}
```

## 实现示例

```java
@Service
@RequiredArgsConstructor
public class OrderServiceImpl implements OrderService {
    private final OrderMapper orderMapper;

    @Override
    public Order getById(Long id) {
        return orderMapper.findById(id);
    }
}
```

## 异常与校验

- 资源不存在时抛出 `ResponseStatusException(HttpStatus.NOT_FOUND)` 或自定义业务异常。
- 入参校验可在 Service 层调用 `Objects.requireNonNull` 或 JSR-380（`@Valid` 在 Controller 触发）。

## 事务

- 多表写操作在 Service 方法上加 `@Transactional(rollbackFor = Exception.class)`。
- 只读查询可加 `@Transactional(readOnly = true)`。

## 与 Controller 协作

- Service 返回领域对象或 DTO，不返回 `ResponseEntity`。
- 列表查询返回 `List<Entity>` 或分页对象（后续可接 Spring Data）。
