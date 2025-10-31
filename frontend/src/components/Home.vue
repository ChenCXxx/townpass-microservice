<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { hello, echo, listUsers, createUser, listTestRecords, createTestRecord } from '@/service/api'

const hi = ref(null)          // GET /api/hello 回傳
const echoMsg = ref('ping')   // POST /api/echo 輸入
const echoResp = ref(null)    // POST /api/echo 回傳

const users = ref([])         // GET /api/users 回傳
const newName = ref('Alice')  // POST /api/users 的 name

const tests = ref([])         // GET /api/test_records 回傳
const newTestTitle = ref('Sample title')
const newTestDescription = ref('A short description')

const loading = ref(false)
const error = ref('')
const router = useRouter()

onMounted(async () => {
  try {
    loading.value = true
    error.value = ''
    hi.value = await hello()
    users.value = await listUsers()
    tests.value = await listTestRecords()
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
})

async function sendEcho() {
  try {
    loading.value = true
    error.value = ''
    echoResp.value = await echo(echoMsg.value)
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function addUser() {
  try {
    loading.value = true
    error.value = ''
    await createUser({ name: newName.value })
    users.value = await listUsers()   // 重新抓清單
    newName.value = ''
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function addTestRecord() {
  try {
    loading.value = true
    error.value = ''
    await createTestRecord({ title: newTestTitle.value, description: newTestDescription.value })
    tests.value = await listTestRecords()
    newTestTitle.value = ''
    newTestDescription.value = ''
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

function goToMap() {
  router.push('/map')
}
</script>

<template>
  <section class="grid gap-4 max-w-[720px] mx-auto p-4">
    <h1 class="text-3xl font-bold">Home</h1>

    <div v-if="loading" class="text-gray-500">Loading…</div>
    <div v-if="error" class="text-red-600">Error: {{ error }}</div>

    <!-- 1) 測試 GET /api/hello -->
    <article class="border border-gray-200 rounded-lg p-3">
      <h3 class="font-semibold mb-2">GET /api/hello</h3>
      <pre class="bg-gray-100 p-2 rounded overflow-auto">{{ hi }}</pre>
    </article>

    <!-- 2) 測試 POST /api/echo（用來驗證 CORS） -->
    <article class="border border-gray-200 rounded-lg p-3">
      <h3 class="font-semibold mb-2">POST /api/echo</h3>
      <div class="flex items-center gap-2">
        <input v-model="echoMsg" placeholder="type a message" class="px-2 py-1 border border-gray-300 rounded" />
        <button @click="sendEcho" class="px-3 py-1 border border-gray-400 rounded hover:border-indigo-500">Send</button>
      </div>
      <pre class="bg-gray-100 p-2 rounded mt-2 overflow-auto">{{ echoResp }}</pre>
    </article>

    <!-- Mapbox 導覽 -->
    <article class="border border-gray-200 rounded-lg p-3">
      <h3 class="font-semibold mb-2">Map</h3>
      <button @click="goToMap" class="px-3 py-1 border border-gray-400 rounded hover:border-indigo-500">前往地圖頁面</button>
    </article>

    <!-- 3) 測試 /api/users 清單 + 建立 -->
    <article class="border border-gray-200 rounded-lg p-3">
      <h3 class="font-semibold mb-2">Users</h3>
      <div class="flex items-center gap-2">
        <input v-model="newName" placeholder="name" class="px-2 py-1 border border-gray-300 rounded" />
        <button @click="addUser" class="px-3 py-1 border border-gray-400 rounded hover:border-indigo-500">Add</button>
      </div>
      <ul class="mt-2 list-disc pl-6">
        <li v-for="u in users" :key="u.id">{{ u.id }} — {{ u.name }}</li>
      </ul>
    </article>

    <!-- 4) 測試 /api/test_records 清單 + 建立 -->
    <article class="border border-gray-200 rounded-lg p-3">
      <h3 class="font-semibold mb-2">Test Records</h3>
      <div class="flex items-center flex-wrap gap-2">
        <input v-model="newTestTitle" placeholder="title" class="flex-1 min-w-[200px] px-2 py-1 border border-gray-300 rounded" />
        <input v-model="newTestDescription" placeholder="description" class="flex-[2] min-w-[200px] px-2 py-1 border border-gray-300 rounded" />
        <button @click="addTestRecord" class="px-3 py-1 border border-gray-400 rounded hover:border-indigo-500">Add Test</button>
      </div>
      <ul class="mt-2 list-disc pl-6">
        <li v-for="t in tests" :key="t.id">{{ t.id }} — <strong>{{ t.title }}</strong> — {{ t.description }}</li>
      </ul>
    </article>
  </section>
</template>

<style scoped>
</style>
