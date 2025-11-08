<script setup>
const props = defineProps({
  active: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['select'])

function select(tab) {
  emit('select', tab)
}
</script>

<template>
  <nav class="flex border-b border-gray-200 bg-white">
    <!-- 地圖 -->
    <button
      type="button"
      class="flex-1 py-3 text-center text-base"
      :class="props.active === 'map' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="select('map')"
    >地圖</button>
    <!-- 公告（與收藏交換位置） -->
    <button
      type="button"
      class="flex-1 py-3 text-center text-base"
      :class="props.active === 'announcement' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="select('announcement')"
    >公告</button>
    <!-- 收藏 -->
    <button
      type="button"
      class="flex-1 py-3 text-center text-base"
      :class="props.active === 'recommend' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="select('recommend')"
    >收藏</button>
  </nav>
</template>
