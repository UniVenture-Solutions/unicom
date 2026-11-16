import { createApp } from 'vue'
import { setConfig } from 'frappe-ui'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
setConfig('resourceFetcher', async ({url, params, method = 'GET'}) => {
  const opts = {method, headers: {'Content-Type':'application/json','X-Frappe-CSRF-Token':window.csrf_token || ''}}
  if (method !== 'GET') opts.body = JSON.stringify(params || {})
  else if (params) url += '?' + new URLSearchParams(params)
  const res = await fetch(url, opts); const data = await res.json(); if (!res.ok) throw new Error(data.exception || 'Request failed'); return data.message
})
createApp(App).use(createRouter({ history: createMemoryHistory(), routes: [] })).mount('#app')
