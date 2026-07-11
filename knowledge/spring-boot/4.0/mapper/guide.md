# Spring Boot 4.0 Mapper 层（MyBatis）指南

## 包结构与命名

- 接口放在 `com.example.demo.mapper` 包。
- 命名 `{Entity}Mapper`，如 `OrderMapper`。
- 使用 `@Mapper` 注解，启动类加 `@MapperScan("com.example.demo.mapper")`。

## 基础 CRUD 接口示例

```java
@Mapper
public interface OrderMapper {
    Order findById(@Param("id") Long id);

    List<Order> findAll();

    int insert(Order order);

    int update(Order order);

    int deleteById(@Param("id") Long id);
}
```

## XML 映射文件

- 路径：`src/main/resources/mapper/OrderMapper.xml`
- `namespace` 必须与接口全限定名一致。
- `resultType` 或 `resultMap` 指向 entity 包中的实体类。

```xml
<select id="findById" resultType="com.example.demo.entity.Order">
    SELECT id, name, created_at AS createdAt
    FROM orders WHERE id = #{id}
</select>
```

## 与 Entity 对齐

- SQL 列名与实体属性一致或通过别名映射。
- `insert` 使用 `useGeneratedKeys="true" keyProperty="id"` 回填主键。

## 配置要点

```yaml
mybatis:
  mapper-locations: classpath:mapper/*.xml
  configuration:
    map-underscore-to-camel-case: true
```
