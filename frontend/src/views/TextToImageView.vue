<template>
  <h1 class="page-title">文生图</h1>
  <GenerationWorkspace
    endpoint="text-to-image"
    task-type="text-to-image"
    title="文字生成图片"
    prompt-placeholder="描述画面：海报、概念图、摄影素材…"
  />
</template>

<script setup lang="ts">
import GenerationWorkspace from '../components/GenerationWorkspace.vue'
</script>
