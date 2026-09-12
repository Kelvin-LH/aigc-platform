<template>
  <div class="card">
    <h3>{{ title }}</h3>
    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" @close="error = ''" />

    <!-- 参考图上传（图生图 / 图生视频） -->
    <div v-if="needImage" style="margin-bottom: 14px">
      <div class="muted" style="margin-bottom: 6px">参考图片（支持拖拽/粘贴，从素材库复用）</div>
      <el-upload
        drag
        :auto-upload="false"
        :show-file-list="false"
        accept="image/png,image/jpeg,image/webp,image/bmp"
        :on-change="onPickImage"
      >
        <div v-if="asset" style="padding: 6px">
          <img :src="previewUrl" style="max-height: 140px; border-radius: 6px" alt="参考图" />
          <div class="muted">{{ asset.filename }}（{{ (asset.size_bytes / 1024).toFixed(0) }} KB）</div>
        </div>
        <div v-else style="padding: 24px 0">
          <div style="font-size: 26px">📤</div>
          <div class="muted">点击或拖拽图片到此处上传</div>
        </div>
      </el-upload>
    </div>

    <!-- Prompt 输入 -->
    <el-form label-position="top">
      <el-form-item :label="needImage ? '编辑指令 / 运动描述' : 'Prompt'">
        <el-input v-model="prompt" type="textarea" :rows="3"
                  :placeholder="promptPlaceholder" />
      </el-form-item>
      <el-form-item label="负面 Prompt（可选）">
        <el-input v-model="negativePrompt" type="textarea" :rows="1" placeholder="不希望出现的元素" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="质量模式">
            <el-select v-model="modelProfile">
              <el-option label="快速（轻量档）" value="fast" />
              <el-option label="标准" value="standard" />
              <el-option label="高质量（大模型档）" value="high" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="优先级">
            <el-select v-model="priority">
              <el-option v-for="p in [1, 3, 5, 7, 9]" :key="p" :value="p"
                         :label="p === 1 ? '最高' : p === 9 ? '最低' : String(p)" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="Seed（可选）">
            <el-input-number v-model="seed" :min="0" style="width: 100%" placeholder="随机" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-collapse v-if="showAdvanced">
        <el-collapse-item title="高级设置（采样步数 / CFG / 时长 / FPS）">
          <el-row :gutter="12">
            <el-col :span="6"><el-input v-model="params.steps" placeholder="采样步数" /></el-col>
            <el-col :span="6"><el-input v-model="params.cfg" placeholder="CFG" /></el-col>
            <el-col :span="6"><el-input v-model="params.duration" placeholder="时长(秒)" /></el-col>
            <el-col :span="6"><el-input v-model="params.fps" placeholder="FPS" /></el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>

      <div style="margin-top: 16px; display: flex; gap: 10px; align-items: center">
        <el-button type="primary" size="large" :loading="submitting" @click="submit">
          {{ submitting ? '已提交…' : '开始生成' }}
        </el-button>
        <span class="muted">提交后立即返回 task_id，可在右侧任务队列跟踪进度</span>
      </div>
    </el-form>
  </div>

  <!-- 进度卡片 -->
  <div class="card" v-if="task">
    <h3>任务进度
      <el-tag size="small" style="margin-left: 8px" :type="(statusType as any)">{{ statusLabel }}</el-tag>
    </h3>
    <el-progress :percentage="progress" :stroke-width="14" striped flow />
    <div class="stage-flow" style="margin-top: 12px">
      <template v-for="(s, i) in stageFlow" :key="s">
        <span class="stage-chip"
              :class="{ done: i < currentStageIndex, active: i === currentStageIndex && running }">{{ s }}</span>
        <span v-if="i < stageFlow.length - 1" class="muted">→</span>
      </template>
    </div>
    <div v-if="task.gpu_ids" class="muted" style="margin-top: 10px">
      模型：{{ task.model_key }} · 资源档位：{{ task.resource_profile }} · GPU：{{ task.gpu_ids }}
    </div>
    <div v-if="task.error_code" style="color: #d9534f; margin-top: 8px">
      失败：{{ task.error_code }} <el-button size="small" link type="primary" @click="retry">重试</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, subscribeTaskEvents } from '../api/client'
import {
  STATUS_LABELS, STATUS_TYPES, TASK_TYPE_LABELS,
  type AssetOut, type TaskEvent, type TaskOut
} from '../api/types'

const props = defineProps<{
  endpoint: string
  taskType: string
  title: string
  needImage?: boolean
  promptPlaceholder?: string
}>()

const showAdvanced = computed(() => ['image-to-video', 'text-to-video'].includes(props.taskType))
const stageFlow = computed(() =>
  props.taskType === 'text-to-text'
    ? ['排队', '分配 GPU', '加载模型', 'Prompt 编码', '文本生成', '写回历史']
    : props.needImage
      ? ['排队', '分配 GPU', '加载模型', '图像编码', '扩散采样', 'VAE 解码', '上传']
      : ['排队', '分配 GPU', '加载模型', 'Prompt 编码', '扩散采样', 'VAE 解码', '上传']
)

const prompt = ref('')
const negativePrompt = ref('')
const modelProfile = ref('standard')
const priority = ref(5)
const seed = ref<number | undefined>(undefined)
const params = ref<Record<string, string>>({})
const asset = ref<AssetOut | null>(null)
const submitting = ref(false)
const error = ref('')
const task = ref<TaskOut | null>(null)
const event = ref<TaskEvent | null>(null)
let es: EventSource | undefined

const previewUrl = computed(() => asset.value ? `/files/uploads/${asset.value.uri.split('/').pop()}` : '')
const progress = computed(() => event.value?.progress ?? task.value?.progress ?? 0)
const running = computed(() => task.value?.status === 'RUNNING')
const statusLabel = computed(() => STATUS_LABELS[task.value?.status ?? ''] ?? task.value?.status)
const statusType = computed(() => STATUS_TYPES[task.value?.status ?? ''] ?? 'info')
const currentStageIndex = computed(() => {
  const stage = event.value?.stage ?? ''
  const idx = stageFlow.value.findIndex(s => stage.includes(s.slice(0, 2)))
  return idx >= 0 ? idx : 0
})

async function onPickImage(file: any) {
  try {
    asset.value = await api.uploadAsset(file.raw)
    ElMessage.success('图片已上传')
  } catch (e: any) {
    error.value = e.message ?? '上传失败'
  }
}

async function submit() {
  error.value = ''
  if (props.needImage && !asset.value) { error.value = '请先上传参考图片'; return }
  if (!prompt.value.trim() && props.taskType !== 'image-to-image') { error.value = '请输入 Prompt'; return }
  submitting.value = true
  try {
    const cleanParams = Object.fromEntries(Object.entries(params.value).filter(([, v]) => v !== ''))
    task.value = await api.submitTask(props.endpoint, {
      task_type: props.taskType,
      input_asset_ids: asset.value ? [asset.value.id] : [],
      prompt: prompt.value,
      negative_prompt: negativePrompt.value,
      model_profile: modelProfile.value,
      priority: priority.value,
      generation_params: { ...cleanParams, ...(seed.value != null ? { seed: seed.value } : {}) }
    })
    ElMessage.success(`已提交，task_id: ${task.value.id.slice(0, 8)}…`)
    track(task.value.id)
  } catch (e: any) {
    error.value = e.message ?? '提交失败'
  } finally {
    submitting.value = false
  }
}

function track(id: string) {
  es?.close()
  event.value = null
  es = subscribeTaskEvents(id, (e) => {
    event.value = e
  })
}

async function retry() {
  if (!task.value) return
  try {
    task.value = await api.retryTask(task.value.id)
    track(task.value.id)
  } catch (e: any) {
    error.value = e.message
  }
}

onBeforeUnmount(() => es?.close())
</script>
