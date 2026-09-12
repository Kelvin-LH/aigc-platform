<template>
  <h1 class="page-title">图生图（指令式编辑）</h1>
  <GenerationWorkspace
    endpoint="image-edit"
    task-type="image-to-image"
    title="参考图 + 编辑指令"
    need-image
    prompt-placeholder="自然语言编辑，例如：保留人物，替换背景为雪山日落"
  />
</template>

<script setup lang="ts">
import GenerationWorkspace from '../components/GenerationWorkspace.vue'
</script>
