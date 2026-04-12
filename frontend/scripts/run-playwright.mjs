import { spawn } from 'node:child_process'

const isWindows = process.platform === 'win32'
const forwardedArgs = process.argv.slice(2)

const selectedPort =
  process.env.PLAYWRIGHT_PORT ?? String(41730 + Math.floor(Math.random() * 1000))
const env = {
  ...process.env,
  PLAYWRIGHT_PORT: selectedPort,
}

function quoteArg(value) {
  return /[\s"]/u.test(value) ? `"${value.replaceAll('"', '\\"')}"` : value
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn([command, ...args.map(quoteArg)].join(' '), {
      stdio: 'inherit',
      shell: true,
      env,
    })

    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`${command} exited with code ${code ?? 'null'}`))
    })
  })
}

try {
  await run('bun', ['run', 'build'])
  await run('bunx', ['playwright', 'test', '--config', 'playwright.config.ts', ...forwardedArgs])
} catch (error) {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
}
