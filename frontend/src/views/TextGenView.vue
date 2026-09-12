<template>
  <h1 class="page-title">文生文</h1>
  <GenerationWorkspace
    endpoint="text"
    task-type="text-to-text"
    title="Prompt / 模板 / 参考文本"
    prompt-placeholder="输入创作需求：文案、脚本、标题、提示词增强…"
  />
</template>

<script setup lang="ts">
import GenerationWorkspace from '../components/GenerationWorkspace.vue'
</script>
