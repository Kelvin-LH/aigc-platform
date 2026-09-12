<template>
  <h1 class="page-title">图生视频</h1>
  <GenerationWorkspace
    endpoint="image-to-video"
    task-type="image-to-video"
    title="参考图 + 运动描述"
    need-image
    prompt-placeholder="描述镜头运动与画面变化：镜头缓慢推进，人物轻微转头…"
  />
</template>

<script setup lang="ts">
import GenerationWorkspace from '../components/GenerationWorkspace.vue'
</script>
