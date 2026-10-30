import { defineConfig } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'
const target = new URL(baseURL)
if (target.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(target.hostname)) {
  throw new Error('浏览器测试只允许连接本地开发服务')
}

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.browser.cjs',
  reporter: 'line',
  use: {
    baseURL,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    headless: true,
  },
})
