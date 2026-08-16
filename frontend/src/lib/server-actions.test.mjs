import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const appRoot = path.resolve(here, '../app')

async function typescriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []

  for (const entry of entries) {
    const location = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      files.push(...(await typescriptFiles(location)))
    } else if (/\.tsx?$/.test(entry.name)) {
      files.push(location)
    }
  }

  return files
}

test('use server modules expose only async runtime exports', async () => {
  const files = await typescriptFiles(appRoot)
  const violations = []

  for (const file of files) {
    const source = await readFile(file, 'utf8')
    if (!/^['"]use server['"];?/m.test(source)) continue

    const forbiddenPatterns = [
      /export\s+(?:const|let|var|class|enum)\s+([A-Za-z_$][\w$]*)/g,
      /export\s+function\s+([A-Za-z_$][\w$]*)/g,
    ]

    for (const pattern of forbiddenPatterns) {
      for (const match of source.matchAll(pattern)) {
        violations.push(`${path.relative(appRoot, file)}: ${match[1]}`)
      }
    }
  }

  assert.deepEqual(
    violations,
    [],
    `use server modules must not export non-async runtime values:\n${violations.join('\n')}`,
  )
})
