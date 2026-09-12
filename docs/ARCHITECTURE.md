# 架构设计

依据《AIGC 多模态智能生成平台建设方案（8×V100 部署版）V1.0》。

## 1. 分层

| 层级 | 组件 | 职责 |
|------|------|------|
| 用户与入口层 | Web 创作端、管理后台、开放 API | 创作界面、账号、项目/素材访问 |
| 接入与安全层 | Nginx、JWT/RBAC、审核 | TLS、鉴权、限流、文件校验、审计 |
| 业务服务层 | 项目/素材/任务/结果管理 | 创作需求 → 标准 TaskSpec |
| 编排与调度层 | Scheduler、GPU Resource Manager | 排队、资源锁、GPU 组分配、重试、进度回调 |
| 模型服务层 | LLM/I2I/I2V/T2V Worker | 封装模型与推理参数，只负责推理 |
| 基础设施层 | 8×V100、PostgreSQL、Redis、MinIO、Prometheus | 计算、元数据、存储、指标 |

## 2. 关键决策

### 业务层不直接调用模型进程
所有生成请求先写入任务中心（`tasks` 表 + 优先级队列），Scheduler 按模型/显存/优先级/
GPU 占用分配 Worker。模型可独立升级，Web 请求不被分钟级视频推理阻塞。

### GPU 资源池（gang scheduling）
- V100 无 MIG，进程级隔离：`CUDA_VISIBLE_DEVICES` + 分布式锁 + NCCL
- 档位 S(1)/M(2)/L(4)/XL(8)，整组 GPU 同时获取/释放，不做碎片式抢占
- XL 任务等待整机空闲（drain 低优先级 Worker 后整组执行）
- 实现：`backend/app/scheduler/gpu_manager.py`（开发模式进程内 asyncio；
  生产模式切换 Redis 分布式锁，`USE_REDS=true`）

### TaskSpec 与 Adapter
统一任务规格 `TaskSpec`（task_type、input_assets、prompt、model_profile、params…），
模型侧 Adapter 将其转换为具体仓库的 CLI/Python 参数。业务服务不绑定模型实现。

### V100 兼容性（Compatibility Profile）
每个模型记录：dtype、attention backend、最小 GPU 数、峰值显存、offload/多卡支持。
- 生产默认 FP16，禁用 FP8/Hopper 专用算子
- BF16-only 参考实现（如 Wan2.2）先小样本一致性验证
- Wan2.2 A14B 独立 Python 环境锁定依赖
- Worker 启动自检：CUDA/NCCL、权重校验、显存基线、固定 seed golden sample

## 3. 任务状态机

```
CREATED → VALIDATING → QUEUED → ALLOCATING → RUNNING → ENCODING → UPLOADING → SUCCEEDED
异常: FAILED（可 retry，保留原始参数与模型版本）；用户取消: CANCELED
```

运行中结构化阶段（前端展示而非笼统“生成中”）：
排队 → 分配 GPU → 加载模型 → Prompt 编码 → 扩散采样 → VAE 解码 → 视频编码 → 上传

## 4. 数据与存储

| 数据 | 位置 |
|------|------|
| 用户/项目/任务元数据 | PostgreSQL（模型版本、参数、seed、审计字段） |
| 原图/结果图/视频 | MinIO（UUID 路径；开发模式本地 `results/`） |
| 队列/锁/短期状态 | Redis（优先级队列、GPU 锁、Worker 心跳） |
| 模型权重 | 本地 NVMe 只读目录，SHA256 校验 |
| 日志/指标 | 文件/Loki + Prometheus/Grafana + DCGM Exporter |

核心数据表见 `README.md` 附录（users / projects / assets / tasks / task_inputs /
task_outputs / models / audit_logs）。

## 5. 可追溯性
每个输出保存：模型名/版本、seed、参数、输入 asset hash、创建者、任务 ID、时间。
