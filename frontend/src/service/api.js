const BASE = import.meta.env.VITE_API_BASE || ''

export async function hello() {
    const res = await fetch(`${BASE}/api/hello`)
    return res.json()
}

export async function echo(message) {
  const r = await fetch(`${BASE}/api/echo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  })
  return r.json()
}

export const listUsers = () => 
    fetch(`${BASE}/api/users`).then(r=>r.json())

export const createUser = (p) =>
    fetch(`${BASE}/api/users`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(p)
    }).then(r=>r.json())

export const listTestRecords = () =>
  fetch(`${BASE}/api/test_records`).then(r=>r.json())

export const createTestRecord = (p) =>
  fetch(`${BASE}/api/test_records`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(p)
  }).then(r=>r.json())