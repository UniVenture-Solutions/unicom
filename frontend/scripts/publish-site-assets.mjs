import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const site = process.argv[2]
if (!site || process.argv.length !== 3) throw new Error('Usage: node scripts/publish-site-assets.mjs /absolute/path/to/site')
if (!path.isAbsolute(site)) throw new Error('Site path must be absolute')
await fs.access(path.join(site, 'site_config.json'))
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const source = path.join(root, 'unicom', 'public', 'frontend', 'assets')
const destination = path.join(site, 'public', 'files', 'unicom', 'frontend', 'assets')
await fs.access(source)
await fs.mkdir(destination, { recursive: true })
await fs.cp(source, destination, { recursive: true })
console.log(`Published frontend assets to ${destination}`)
