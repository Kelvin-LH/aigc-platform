<template>
  <h1 class="page-title">文生视频</h1>
  <GenerationWorkspace
    endpoint="text-to-video"
    task-type="text-to-video"
    title="文字生成视频"
    prompt-placeholder="描述画面内容与镜头语言，支持负面 Prompt 与分镜模式"
  />
</template>

<script setup lang="ts">
import GenerationWorkspace from '../components/GenerationWorkspace.vue'
</script>
