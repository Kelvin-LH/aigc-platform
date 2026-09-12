// 后端 API 类型定义（对应 FastAPI schemas）
export interface TaskOut {
  id: string
  project_id: number | null
  user_id: number
  task_type: string
  model_key: string
  model_version: string
  status: string
  priority: number
  resource_profile: string
  progress: number
  stage: string
  gpu_ids: string
  error_code: string | null
  created_at?: string
  updated_at?: string
}

export interface TaskEvent {
  task_id: string
  status: string
  stage: string
  progress: number
  gpu_ids?: string
  error_code?: string | null
}

export interface AssetOut {
  id: number
  project_id: number | null
  owner_id: number
  type: string
  filename: string
  uri: string
  sha256: string
  size_bytes: number
  mime: string
  created_at?: string
}

export interface ModelOut {
  id: number
  capability: string
  name: string
  version: string
  quality_tier: string
  resource_profile: string
  dtype: string
  min_gpus: number
  license: string
  enabled: boolean
  health: string
  adapter: string
}

export const TASK_TYPE_LABELS: Record<string, string> = {
  'text-to-text': '文生文',
  'image-to-image': '图生图',
  'image-to-video': '图生视频',
  'text-to-video': '文生视频',
  'text-to-image': '文生图'
}

export const STATUS_LABELS: Record<string, string> = {
  CREATED: '已创建', VALIDATING: '校验中', QUEUED: '排队中', ALLOCATING: '分配 GPU',
  RUNNING: '推理中', ENCODING: '编码中', UPLOADING: '上传中',
  SUCCEEDED: '已完成', FAILED: '失败', CANCELED: '已取消'
}

export const STATUS_TYPES: Record<string, string> = {
  SUCCEEDED: 'success', FAILED: 'danger', CANCELED: 'info',
  RUNNING: 'primary', ALLOCATING: 'warning', QUEUED: 'info'
}

export const PROFILE_LABELS: Record<string, string> = {
  S: '轻量 1卡', M: '中量 2卡', L: '重量 4卡', XL: '超重 8卡', API: '外部API · 0卡'
}
