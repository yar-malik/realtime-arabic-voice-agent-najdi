/**
 * Talk to a Saudi Arabic phone agent and hear it answer.
 *
 * No dependencies and no build step — Node 18 or newer.
 *
 *   export VOHO_API_KEY=voho_sk_live_...   # app.voho.ai -> API Tokens
 *   npm start
 *
 * New accounts start with $25 of credit, so this costs nothing to try.
 */
const KEY = process.env.VOHO_API_KEY
const BASE = process.env.VOHO_BASE_URL ?? 'https://app.voho.ai'

if (!KEY) {
  console.error('Set VOHO_API_KEY first — create one at https://app.voho.ai/tokens')
  process.exit(1)
}

async function voho(path, body, raw = false) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    console.error(`${detail.error?.code ?? res.status}: ${detail.error?.message ?? 'request failed'}`)
    process.exit(1)
  }
  return raw ? Buffer.from(await res.arrayBuffer()) : res.json()
}

function spent(cents) {
  console.log(`\nCharged $${(cents / 100).toFixed(2)} from your Voho balance.`)
}

const { writeFile } = await import('node:fs/promises')

const said = process.argv.slice(2).join(' ') || 'وش سياسة الاسترجاع عندكم؟'
const agentId = process.env.VOHO_AGENT_ID

if (!agentId) {
  // No agent configured yet: speak the line so you hear the voice, and say
  // where to make an agent that can answer back.
  console.log('VOHO_AGENT_ID is not set — speaking a line instead.\n')
  const audio = await voho('/v1/speech', { text: 'أهلاً بك، معك ليلى. كيف أقدر أساعدك؟', voice: 'layla', model: 'sada-1', format: 'mp3' }, true)
  await writeFile('voho.mp3', audio)
  console.log('Wrote voho.mp3 — play it.')
  console.log('\nTo have a conversation: create an agent at https://app.voho.ai/agents,')
  console.log('copy its id from the URL, then: export VOHO_AGENT_ID=...')
  process.exit(0)
}

console.log(`Caller: ${said}`)
const out = await voho(`/v1/agents/${agentId}/reply`, {
  text: said,
  variables: { company: process.env.VOHO_COMPANY ?? 'شركتنا' },
})

console.log(`Agent : ${out.reply}`)
if (out.audio) {
  await writeFile('reply.mp3', Buffer.from(out.audio, 'base64'))
  console.log('\nWrote reply.mp3 — that is what the caller would hear.')
}
spent(out.cost_cents)
