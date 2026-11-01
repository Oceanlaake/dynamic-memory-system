# 接口越界参数检查

接口：POST /api/query
运行模式：Hybrid 检索 + hybrid Resolver（DeepSeek 配置启用）

| 参数 | 输入 | 允许范围 | HTTP 状态 | 结果 |
|---|---:|---|---|---|
| top_k | 51 | 1–50 | 422 | 正确拒绝 |
| max_expansion_memories | 201 | 1–200 | 422 | 正确拒绝 |

两次均返回 INVALID_REQUEST，错误字段与上限提示正确。
响应 JSON 和 HTTP 状态日志保存在本目录的 api-invalid-* 文件中。
