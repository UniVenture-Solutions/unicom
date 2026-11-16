import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

// Sites whose proxy does not serve bench assets can publish the same build under /files.
const base = process.env.UNICOM_ASSET_BASE || '/assets/unicom/frontend/'
if (!['/assets/unicom/frontend/', '/files/unicom/frontend/'].includes(base)) {
  throw new Error('Unsupported UNICOM_ASSET_BASE')
}
export default defineConfig({ plugins: [frappeui(), vue()], base, build: { outDir: '../unicom/public/frontend', emptyOutDir: true } })
