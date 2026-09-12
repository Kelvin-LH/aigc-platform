# AIGC 多模态智能生成平台（8× V100）

面向 8× NVIDIA Tesla V100（SXM2/NVLink）服务器的统一多模态 AIGC 生成平台。

**核心能力**：文生文 · 图生图 · 图生视频 · 文生视频 · 文生图

## 架构总览

```
用户与入口层   Vue 3 + Element Plus（统一创作入口 / 管理后台 / 开放 API）
接入与安全层   Nginx · JWT/RBAC · 上传校验 · 审计
业务服务层     FastAPI：项目 / 素材 / 任务 / 模型管理（标准 TaskSpec）
编排与调度层   优先级队列 + GPU Resource Manager（gang scheduling）
模型服务层     LLM / I2I / I2V / T2V Worker（Adapter 解耦具体模型）
基础设施层     8×V100 · PostgreSQL · Redis · MinIO · Prometheus/Grafana
```

关键原则：**业务层不直接调用模型进程**。所有生成请求写入任务中心，由调度层根据模型、
显存、优先级和 GPU 占用选择 Worker；前端通过 SSE 实时接收结构化阶段进度。

### 并发与调度设计

- **predicate 调度（消除队头阻塞）**：队列条目携带资源档位，队首资源不足时跳过它继续
  调度后续可运行任务——XL 高优任务等待整机空闲期间，S/M/L 小任务正常并发。
- **资源释放唤醒**：任务完成释放 GPU 后主动唤醒调度循环，等待中的 XL 立即重试分配，
  不会出现"空有 8 卡、队列卡死"的丢唤醒死锁。
- **整组 gang scheduling**：S(1)/M(2)/L(4)/XL(8) 档位下同档任务在 8 卡内自然并发
  （如 6×S + 2×M 同时跑满 8 卡）。
- **SQLite 并发加固**（开发模式）：WAL + busy_timeout；生产环境使用 PostgreSQL。
- **SSE 断线补发**：订阅事件流时先补发任务当前状态快照，重连不丢进度。
- **取消语义**：排队任务取消立即落库；运行中任务在阶段边界中断，GPU 必然释放。

## GPU 资源档位（8×V100 16GB）

| 档位 | 占用 | 适合任务 | 策略 |
|------|------|----------|------|
| S | 1 卡 | 文生文、Prompt 扩展 | 常驻 Worker，可被高优视频驱逐 |
| M | 2 卡 | 图片编辑/生成、较大 LLM | 并发 1–2 任务 |
| L | 4 卡 | 标准视频、高质量图片 | 资源锁 + 整组获取/释放 |
| XL | 8 卡 | Wan2.2 A14B 高质量视频 | 独占整机（gang scheduling） |

V100 不支持 MIG：采用进程级 GPU 隔离（`CUDA_VISIBLE_DEVICES`）+ 分布式锁 + NCCL。

## 模型方案

| 能力 | 默认后端 | 高质量后端 | V100 适配 |
|------|----------|-----------|-----------|
| 文生文 | Qwen2.5-3B/7B | Qwen2.5-14B | FP16，1–2 卡 |
| 图生图 | SDXL+ControlNet | FLUX.1 Kontext [dev] | FP16 + CPU offload |
| 文生图 | SDXL | FLUX.1 Krea [dev] | FP16 + offload |
| 图生视频 | Wan2.2 TI2V-5B | Wan2.2 I2V-A14B | FP16；A14B 走 8 卡 FSDP+Ulysses |
| 文生视频 | Wan2.2 T2V-5B | Wan2.2 T2V-A14B | 同上 |

兼容性策略：默认 FP16 路径，禁用 FP8/Hopper 专用算子；A14B 使用独立 Python 环境锁定依赖；
每种 Worker 启动自检（CUDA/NCCL、权重校验、显存基线、golden sample）。

## 快速开始（本地开发）

```bash
# 后端（零外部依赖，SQLite + 进程内队列 + 模拟 Worker）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8600
# 默认账号：admin / admin123

# 前端
cd frontend
npm install
npm run dev     # http://localhost:5173（已代理 /api 到 8600）
```

打开 http://localhost:5173 ，登录后即可提交四类生成任务，右侧任务面板实时查看
排队 → 分配 GPU → 加载模型 → 采样 → 上传的结构化进度。

## 生产部署（8×V100 服务器）

```bash
docker compose up -d --build
# PostgreSQL + Redis + MinIO + FastAPI + Nginx + Prometheus
# GPU Worker 接入真实模型时，按资源档位拆分容器并指定 CUDA device_ids
```

## 任务状态机

```
CREATED → VALIDATING → QUEUED → ALLOCATING → RUNNING → ENCODING → UPLOADING → SUCCEEDED
                                                ↘ FAILED / CANCELED（可重试，保留原始参数与模型版本）
```

## API 一览

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate/text` | POST | 文生文（SSE 流式 `/generate/text/stream/{id}`） |
| `/api/v1/generate/image-edit` | POST | 图生图 |
| `/api/v1/generate/image-to-video` | POST | 图生视频 |
| `/api/v1/generate/text-to-video` | POST | 文生视频 |
| `/api/v1/tasks/{id}` | GET | 查询状态/阶段/进度 |
| `/api/v1/tasks/{id}/events` | GET | SSE 进度事件流 |
| `/api/v1/tasks/{id}/cancel` \| `retry` | POST | 取消 / 重试 |
| `/api/v1/assets` | POST/GET | 素材上传与查询 |
| `/api/v1/models` | GET | 模型档位与健康状态 |
| `/api/v1/monitor/gpus` | GET | GPU 资源池状态 |

完整交互式文档：`http://localhost:8600/docs`（OpenAPI 自动生成）。

## 目录结构

```
backend/    FastAPI 应用（api / models / scheduler / workers / services）
frontend/   Vue 3 + TS + Element Plus（三栏创作工作区）
deploy/     Prometheus 配置
docs/       架构与 API 文档
docker-compose.yml   单机 8 卡生产部署
```

## 实施路线

- **P0 基础底座**（本仓库已实现）：任务状态机、8 卡资源池、gang scheduling、predicate 并发调度、SSE 进度、素材库、审计（含 `backend/tests/test_concurrency.py` 并发回归测试）
- **P1 文本与图片**：Worker 接入 Qwen / SDXL / FLUX.1 Kontext 真实推理
- **P2 视频**：Wan2.2 TI2V-5B 的 V100 FP16 兼容与接入
- **P3 高质量模式**：A14B 8 卡 FSDP + Ulysses + drain 调度
- **P4 运营**：监控告警、配额、批量任务、模型版本管理

## 参考

- [Wan2.2](https://github.com/Wan-Video/Wan2.2) · [FLUX.1 Kontext](https://github.com/black-forest-labs/flux/blob/main/model_cards/FLUX.1-kontext-dev.md) · [FLUX.1 Krea](https://github.com/black-forest-labs/flux/blob/main/model_cards/FLUX.1-Krea-dev.md) · [NVIDIA V100](https://www.nvidia.com/en-gb/data-center/tesla-v100/)
