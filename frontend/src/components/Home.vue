<script setup>
import { ref, onMounted } from 'vue'
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
</script>

<template>
  <section style="display:grid; gap:16px; max-width:720px">
    <h1>Home</h1>

    <div v-if="loading">Loading…</div>
    <div v-if="error" style="color:#c00">Error: {{ error }}</div>

    <!-- 1) 測試 GET /api/hello -->
    <article style="border:1px solid #ddd; padding:12px; border-radius:8px">
      <h3>GET /api/hello</h3>
      <pre>{{ hi }}</pre>
    </article>

    <!-- 2) 測試 POST /api/echo（用來驗證 CORS） -->
    <article style="border:1px solid #ddd; padding:12px; border-radius:8px">
      <h3>POST /api/echo</h3>
      <input v-model="echoMsg" placeholder="type a message" />
      <button @click="sendEcho">Send</button>
      <pre>{{ echoResp }}</pre>
    </article>

    <!-- 3) 測試 /api/users 清單 + 建立 -->
    <article style="border:1px solid #ddd; padding:12px; border-radius:8px">
      <h3>Users</h3>
      <div style="display:flex; gap:8px; align-items:center">
        <input v-model="newName" placeholder="name" />
        <button @click="addUser">Add</button>
      </div>
      <ul>
        <li v-for="u in users" :key="u.id">{{ u.id }} — {{ u.name }}</li>
      </ul>
    </article>

    <!-- 4) 測試 /api/test_records 清單 + 建立 -->
    <article style="border:1px solid #ddd; padding:12px; border-radius:8px">
      <h3>Test Records</h3>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
        <input v-model="newTestTitle" placeholder="title" style="flex:1; min-width:200px" />
        <input v-model="newTestDescription" placeholder="description" style="flex:2; min-width:200px" />
        <button @click="addTestRecord">Add Test</button>
      </div>
      <ul>
        <li v-for="t in tests" :key="t.id">{{ t.id }} — <strong>{{ t.title }}</strong> — {{ t.description }}</li>
      </ul>
    </article>
  </section>
</template>

<style scoped>
input { padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; }
button { padding: 6px 10px; border: 1px solid #999; border-radius: 6px; cursor: pointer; }
pre { background: #f7f7f7; padding: 8px; border-radius: 6px; overflow: auto; }
</style>
