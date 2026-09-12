# API 设计

Base URL: `/api/v1`　认证: `Authorization: Bearer <JWT>`　交互式文档: `/docs`

## 认证

```http
POST /auth/register  {"username", "password"}           # 注册（默认 creator 角色）
POST /auth/login     {"username", "password"}           # 返回 access_token
GET  /auth/me                                           # 当前用户
```

## 生成

所有生成接口入参为统一 TaskSpec：

```json
{
  "task_type": "text-to-video",
  "project_id": 1,
  "input_asset_ids": [12],
  "prompt": "雪山日落，镜头缓慢推进",
  "negative_prompt": "模糊，变形",
  "model_profile": "standard",
  "generation_params": {"duration": 5, "fps": 16, "seed": 42},
  "priority": 3,
  "callback_url": null
}
```

| 接口 | 方法 | task_type | 特性 |
|------|------|-----------|------|
| `/generate/text` | POST | text-to-text | SSE 流式 |
| `/generate/image-edit` | POST | image-to-image | 需 1 张参考图 |
| `/generate/image-to-video` | POST | image-to-video | 需 1 张参考图 |
| `/generate/text-to-video` | POST | text-to-video | |
| `/generate/text-to-image` | POST | text-to-image | 扩展能力 |

返回：

```json
{"id": "uuid", "status": "QUEUED", "resource_profile": "L", "model_key": "Wan2.2-T2V-5B", ...}
```

`model_profile=high` 的视频任务自动升档为 XL（8 卡整组）。

## 任务

```http
GET  /tasks?status=RUNNING&task_type=image-to-video   # 列表（普通用户仅本人）
GET  /tasks/{id}                                      # 状态/阶段/进度
GET  /tasks/{id}/detail                               # 输入参数 + 输出（seed/版本/耗时）
GET  /tasks/{id}/events                               # SSE 进度事件流
POST /tasks/{id}/cancel                               # 取消排队或运行中任务
POST /tasks/{id}/retry                                # 重试失败/取消任务（保留参数）
```

SSE 事件格式：

```json
{"task_id": "...", "status": "RUNNING", "stage": "扩散采样", "progress": 55, "gpu_ids": "0,1,2,3"}
```

## 素材

```http
POST /assets          # multipart 上传（png/jpeg/webp/bmp/mp4/txt，≤200MB），返回 AssetOut
GET  /assets?type=image
GET  /assets/{id}
DELETE /assets/{id}
```

## 模型

```http
GET   /models                      # 能力 × 质量档位 × Compatibility Profile
PATCH /models/{id}/enabled         # 启停（管理员）
POST  /models/{id}/health-check    # 启动自检（管理员）
```

## 监控

```http
GET /monitor/gpus      # 8 卡空闲/占用 + 档位说明
GET /monitor/queue     # 各状态任务计数
GET /monitor/overview  # 工作台聚合
```

## 错误码

| HTTP | 场景 |
|------|------|
| 401 | 未登录/过期 |
| 403 | 非管理员访问管理接口 |
| 404 | 任务/素材不存在 |
| 409 | 状态冲突（重复取消、不可重试） |
| 413/415 | 上传超限/类型不支持 |
| 422 | TaskSpec 校验失败（prompt 为空、素材缺失） |
| 503 | 能力暂无可用模型 |
