import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
export default defineConfig({plugins:[frappeui(),vue()],base:'/assets/unicom/frontend/',build:{outDir:'../unicom/public/frontend',emptyOutDir:true}})
