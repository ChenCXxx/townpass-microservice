<script setup>
const props = defineProps({
  properties: { type: Object, required: true }
})
</script>

<template>
  <div class="min-w-[240px] max-w-[320px] p-2">
    <div v-if="Object.keys(properties).length === 0">無屬性資料</div>
    <div v-else class="space-y-1">
      <div v-for="(val, key) in properties" :key="key" class="flex gap-2">
        <div class="min-w-[88px] text-gray-500">{{ key }}：</div>
        <div class="text-gray-900 wrap-break-words">{{ val }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>


