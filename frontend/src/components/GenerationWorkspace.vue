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
      <el-form-item>
        <template #label>
          <span>{{ needImage ? '编辑指令 / 运动描述' : 'Prompt（提示词）' }}</span>
          <Tip text="用自然语言描述你想要的内容。生成文字时直接写需求；生成图片/视频时描述画面细节、风格和镜头，越具体效果越好" />
        </template>
        <el-input v-model="prompt" type="textarea" :rows="3"
                  :placeholder="promptPlaceholder" />
      </el-form-item>
      <el-form-item>
        <template #label>
          <span>负面 Prompt（可选）</span>
          <Tip text="你不想在结果里出现的东西。例如填「模糊、变形、文字水印」，系统会尽量避免这些元素" />
        </template>
        <el-input v-model="negativePrompt" type="textarea" :rows="1" placeholder="例如：模糊、变形、水印" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>质量模式</span>
              <Tip text="选择用哪一档模型：快速=小模型，几秒出结果；标准=效果与速度均衡；高质量=最强模型，效果最好但排队更久、耗时更长" />
            </template>
            <el-select v-model="modelProfile">
              <el-option label="快速（小模型，秒级响应）" value="fast" />
              <el-option label="标准（均衡推荐）" value="standard" />
              <el-option label="高质量（最强模型，耗时更长）" value="high" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>优先级</span>
              <Tip text="多任务排队时谁先执行：数字越小越靠前。「最高」相当于插队；普通任务保持默认即可，避免挤占别人的大任务" />
            </template>
            <el-select v-model="priority">
              <el-option v-for="p in [1, 3, 5, 7, 9]" :key="p" :value="p"
                         :label="p === 1 ? '最高（插队执行）' : p === 9 ? '最低（排最后）' : String(p)" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>Seed（随机种子，可选）</span>
              <Tip text="生成的「起点随机数」。留空=每次都随机出新样子；填固定数字并搭配相同参数，可以复现同样/相近的结果，方便在此基础上微调" />
            </template>
            <el-input-number v-model="seed" :min="0" style="width: 100%" placeholder="留空随机" />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 视频任务：时长/分辨率/FPS -->
      <el-row v-if="isVideo" :gutter="12">
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>视频时长</span>
              <Tip text="生成的视频播放长度。时间越长，生成耗时和显存占用越多；建议先用 3–5 秒试效果" />
            </template>
            <el-select v-model="vDuration">
              <el-option label="3 秒（快速试效果）" value="3" /><el-option label="5 秒（推荐）" value="5" />
              <el-option label="8 秒" value="8" /><el-option label="10 秒（最慢）" value="10" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>分辨率</span>
              <Tip text="画面清晰度：480P 出片最快，适合预览挑选；720P 日常够用；1080P 细节最丰富，但生成时间明显变长" />
            </template>
            <el-select v-model="vRes">
              <el-option label="480P（854×480，出片最快）" value="854x480" />
              <el-option label="720P（1280×720，推荐）" value="1280x720" />
              <el-option label="1080P（1920×1080，最清晰）" value="1920x1080" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item>
            <template #label>
              <span>帧率 FPS</span>
              <Tip text="每秒播放多少张画面。帧率越高动作越顺滑：8 帧像翻页动画（草稿），16 帧基本流畅，24 帧接近电影观感" />
            </template>
            <el-select v-model="vFps">
              <el-option label="8（草稿预览）" value="8" /><el-option label="16（标准推荐）" value="16" />
              <el-option label="24（电影级流畅）" value="24" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-collapse v-if="showAdvanced">
        <el-collapse-item title="高级设置（一般保持默认即可）">
          <el-row v-if="isText" :gutter="12">
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>回答长度</span>
                  <Tip text="最多生成多少字（token）。默认 512 字约一页内容，写长文可调大" />
                </template>
                <el-input v-model="pMaxTokens" placeholder="默认 512" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>语气随机度（temperature）</span>
                  <Tip text="0=回答严谨固定，1=更有创意更发散。写文案建议 0.7 左右" />
                </template>
                <el-input v-model="pTemp" placeholder="默认 0.7" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row v-else :gutter="12">
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>采样步数</span>
                  <Tip text="画面从模糊到清晰的「打磨次数」。步数越多细节越好但越慢，一般 20–30 步足够" />
                </template>
                <el-input v-model="pSteps" placeholder="默认 25" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  <span>提示词服从度（CFG）</span>
                  <Tip text="画面有多「听话」：太低会不按你的描述画，太高画面容易生硬。一般 5–8" />
                </template>
                <el-input v-model="pCfg" placeholder="默认 5" />
              </el-form-item>
            </el-col>
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

    <!-- 生成结果 -->
    <div v-if="output" style="margin-top: 14px">
      <div class="muted" style="margin-bottom: 6px">
        生成结果（seed: {{ output.seed }} · 耗时 {{ (output.runtime_ms / 1000).toFixed(1) }}s ·
        模型 {{ output.model_version }}）
        <el-button size="small" link type="primary" :href="output.uri" target="_blank">打开原图/原文</el-button>
      </div>
      <img v-if="isImageOutput" :src="output.uri"
           style="max-width: 100%; max-height: 480px; border-radius: 8px; border: 1px solid #e4e7ed"
           :alt="task.task_type" />
      <pre v-else-if="outputText"
           style="white-space: pre-wrap; background: #f7f8fa; padding: 14px; border-radius: 8px;
                  font-size: 14px; line-height: 1.7; margin: 0">{{ outputText }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, subscribeTaskEvents } from '../api/client'
import Tip from './Tip.vue'
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
const isVideo = computed(() => ['image-to-video', 'text-to-video'].includes(props.taskType))
const isText = computed(() => props.taskType === 'text-to-text')
const vDuration = ref('5')
const vRes = ref('1280x720')
const vFps = ref('16')
const pSteps = ref('')
const pCfg = ref('')
const pMaxTokens = ref('')
const pTemp = ref('')
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
const asset = ref<AssetOut | null>(null)
const submitting = ref(false)
const error = ref('')
const task = ref<TaskOut | null>(null)
const event = ref<TaskEvent | null>(null)
const output = ref<any>(null)
const outputText = ref('')
let es: EventSource | undefined

const isImageOutput = computed(() => !!output.value?.uri?.match(/\.(png|jpe?g|webp)$/i))

async function loadDetail(id: string) {
  try {
    const d: any = await api.getTaskDetail(id)
    const first = d.outputs?.[0]
    if (!first) return
    output.value = first
    if (!isImageOutput.value && first.uri?.endsWith('.txt')) {
      const res = await fetch(first.uri)
      outputText.value = await res.text()
    }
  } catch { /* 静默 */ }
}

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
    const cleanParams: Record<string, unknown> = {}
    if (isVideo.value) {
      cleanParams.duration = vDuration.value
      cleanParams.resolution = vRes.value
      cleanParams.fps = vFps.value
    }
    if (pSteps.value.trim()) cleanParams.steps = pSteps.value.trim()
    if (pCfg.value.trim()) cleanParams.cfg = pCfg.value.trim()
    if (pMaxTokens.value.trim()) cleanParams.max_tokens = pMaxTokens.value.trim()
    if (pTemp.value.trim()) cleanParams.temperature = pTemp.value.trim()
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
  output.value = null
  outputText.value = ''
  es = subscribeTaskEvents(id, (e) => {
    event.value = e
    if (e.status === 'SUCCEEDED') loadDetail(id)
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
