import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const projectDir = path.resolve(frontendDir, '..')
const backendDir = path.join(projectDir, 'backend')
const bundledPython = path.join(projectDir, '.venv', 'Scripts', 'python.exe')
const runtimePort = process.env.ICT_LOCAL_RUNTIME_PORT?.trim() || '8767'
const serveMode = process.argv[2] === 'preview' ? 'preview' : 'dev'
const previewPort = process.env.ICT_PREVIEW_PORT?.trim() || '4173'
const runtimeHealthUrl = `http://127.0.0.1:${runtimePort}/health`
const viteCli = path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')

let localRuntimeProcess = null
let viteProcess = null
let ownsLocalRuntime = false
let shuttingDown = false

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function localRuntimeIsReady() {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 350)
  try {
    const response = await fetch(runtimeHealthUrl, { signal: controller.signal })
    if (!response.ok) return false
    const payload = await response.json()
    return payload?.status === 'ok' && payload?.mode === 'local' && payload?.platform_required === false
  } catch {
    return false
  } finally {
    clearTimeout(timeout)
  }
}

function stopChild(child) {
  if (child && child.exitCode === null && child.signalCode === null) child.kill()
}

async function waitForLocalRuntime() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (await localRuntimeIsReady()) return true
    if (localRuntimeProcess?.exitCode !== null && localRuntimeProcess?.exitCode !== undefined) return false
    await delay(200)
  }
  return false
}

function shutdown(signal) {
  if (shuttingDown) return
  shuttingDown = true
  if (signal) console.info(`收到 ${signal}，正在关闭本地开发进程。`)
  stopChild(viteProcess)
  if (ownsLocalRuntime) stopChild(localRuntimeProcess)
}

process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))

async function main() {
  if (serveMode === 'preview' && !existsSync(path.join(frontendDir, 'dist', 'index.html'))) {
    console.error('未找到生产构建产物，请先运行 npm run build。')
    process.exitCode = 1
    return
  }

  if (!(await localRuntimeIsReady())) {
    const python = existsSync(bundledPython) ? bundledPython : 'python'
    console.info(`正在启动独立本机工作流运行时（127.0.0.1:${runtimePort}）…`)
    localRuntimeProcess = spawn(python, [
      '-m', 'uvicorn', 'app.local_runtime:create_local_runtime_app', '--factory',
      '--app-dir', backendDir, '--host', '127.0.0.1', '--port', runtimePort, '--no-access-log',
    ], { cwd: projectDir, env: process.env, stdio: 'inherit', windowsHide: true })
    ownsLocalRuntime = true
    localRuntimeProcess.once('error', (error) => {
      console.error('启动本机工作流运行时失败。请确认项目虚拟环境和后端依赖已安装。', error)
    })
    if (!(await waitForLocalRuntime())) {
      console.error('本机工作流运行时未能在 12 秒内就绪，已停止启动前端。')
      shutdown()
      process.exitCode = 1
      return
    }
    console.info('本机工作流运行时已就绪；可用组件与运行记录保存在本机。')
  } else {
    console.info(`复用已运行的本机工作流运行时（127.0.0.1:${runtimePort}）。`)
  }

  const viteArgs = serveMode === 'preview'
    ? [viteCli, 'preview', '--host', '127.0.0.1', '--port', previewPort, '--strictPort']
    : [viteCli, '--host', '127.0.0.1']
  const viteEnv = {
    ...process.env,
    VITE_LOCAL_RUNTIME_URL: process.env.VITE_LOCAL_RUNTIME_URL?.trim() || `http://127.0.0.1:${runtimePort}`,
  }
  viteProcess = spawn(process.execPath, viteArgs, {
    cwd: frontendDir,
    env: viteEnv,
    stdio: 'inherit',
    windowsHide: true,
  })
  viteProcess.once('error', (error) => {
    console.error('启动 Vite 开发服务器失败。', error)
    shutdown()
    process.exitCode = 1
  })
  viteProcess.once('exit', (code, signal) => {
    if (signal) console.info(`Vite ${serveMode} 已通过 ${signal} 退出。`)
    shutdown()
    if (code !== null) process.exitCode = code
  })
}

void main().catch((error) => {
  console.error('本地开发环境启动失败。', error)
  shutdown()
  process.exitCode = 1
})
