const assert = require('node:assert/strict')
const test = require('node:test')

const { backendDataDir, parseConfiguredKeys } = require('../electron/backend-process.cjs')

test('parseConfiguredKeys ignores comments and empty values', () => {
  const configured = parseConfiguredKeys(`
    # secrets are never printed
    ANTHROPIC_API_KEY=key
    CLAUDE_MODEL="model"
    SESSION_TOKEN_SECRET='secret'
    SUPERVISOR_PASSPHRASE=
  `)

  assert.deepEqual(
    [...configured],
    ['ANTHROPIC_API_KEY', 'CLAUDE_MODEL', 'SESSION_TOKEN_SECRET'],
  )
})

test('backendDataDir uses LocalAppData and never the installation directory', () => {
  const previous = process.env.LOCALAPPDATA
  process.env.LOCALAPPDATA = 'C:\\Users\\test\\AppData\\Local'
  try {
    assert.equal(
      backendDataDir(),
      'C:\\Users\\test\\AppData\\Local\\SIG Agent\\data',
    )
  } finally {
    if (previous === undefined) delete process.env.LOCALAPPDATA
    else process.env.LOCALAPPDATA = previous
  }
})
