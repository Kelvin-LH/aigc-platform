<template>
  <el-tooltip :content="text" placement="top" effect="dark" :show-after="150">
    <span class="tip-icon">❓</span>
  </el-tooltip>
</template>

<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<style scoped>
.tip-icon {
  margin-left: 6px;
  cursor: help;
  font-size: 12px;
  opacity: 0.55;
}
.tip-icon:hover { opacity: 1; }
</style>
