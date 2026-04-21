import http from 'k6/http'
import { check, group, sleep } from 'k6'

const BASE_URL = (__ENV.K6_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const EMAIL = __ENV.K6_USER_EMAIL || ''
const PASSWORD = __ENV.K6_USER_PASSWORD || ''
const CANARY = (__ENV.K6_CANARY || '').trim() === '1'

function profileOptions(profile) {
  if (profile === 'peak') {
    const rps = Number(__ENV.K6_RPS || 50)
    const duration = __ENV.K6_DURATION || '5m'
    return {
      scenarios: {
        peak: {
          executor: 'constant-arrival-rate',
          rate: rps,
          timeUnit: '1s',
          duration,
          preAllocatedVUs: Math.max(10, Math.ceil(rps / 2)),
          maxVUs: Math.max(50, Math.ceil(rps * 2)),
        },
      },
    }
  }

  if (profile === 'stress') {
    return {
      scenarios: {
        stress: {
          executor: 'ramping-vus',
          startVUs: 0,
          stages: [
            { duration: '2m', target: 25 },
            { duration: '3m', target: 100 },
            { duration: '3m', target: 200 },
            { duration: '2m', target: 0 },
          ],
          gracefulRampDown: '30s',
        },
      },
    }
  }

  if (profile === 'soak') {
    const vus = Number(__ENV.K6_VUS || 25)
    const duration = __ENV.K6_DURATION || '2h'
    return {
      scenarios: {
        soak: {
          executor: 'constant-vus',
          vus,
          duration,
        },
      },
    }
  }

  return {
    scenarios: {
      smoke: {
        executor: 'per-vu-iterations',
        vus: 1,
        iterations: 20,
        maxDuration: '2m',
      },
    },
  }
}

export const options = Object.assign(
  {
    thresholds: {
      http_req_failed: ['rate<0.01'],
      http_req_duration: ['p(50)<200', 'p(95)<500', 'p(99)<1000'],
    },
  },
  profileOptions((__ENV.K6_PROFILE || 'smoke').trim().toLowerCase())
)

export function setup() {
  const headers = { 'content-type': 'application/x-www-form-urlencoded' }
  const canaryHeaders = CANARY ? { 'X-Canary': '1' } : {}
  if (!EMAIL || !PASSWORD) {
    return { token: '', headers: canaryHeaders }
  }

  const body = `username=${encodeURIComponent(EMAIL)}&password=${encodeURIComponent(PASSWORD)}`
  const res = http.post(`${BASE_URL}/api/v1/auth/login`, body, { headers })
  const ok = check(res, {
    'login status 200': (r) => r.status === 200,
    'login has token': (r) => {
      try {
        return Boolean(r.json('access_token'))
      } catch {
        return false
      }
    },
  })
  if (!ok) {
    return { token: '', headers: canaryHeaders }
  }
  const token = res.json('access_token')
  return { token, headers: canaryHeaders }
}

function authHeaders(ctx) {
  const h = Object.assign({}, ctx.headers || {})
  if (ctx.token) {
    h.Authorization = `Bearer ${ctx.token}`
  }
  h.accept = 'application/json'
  return h
}

export default function (ctx) {
  const headers = authHeaders(ctx)

  group('health', () => {
    const res = http.get(`${BASE_URL}/health`, { headers })
    check(res, { 'health 200': (r) => r.status === 200 })
  })

  group('authenticated read path', () => {
    const jobs = http.get(`${BASE_URL}/api/v1/jobs/stats`, { headers })
    check(jobs, { 'jobs stats 200/401': (r) => r.status === 200 || r.status === 401 })

    const contacts = http.get(`${BASE_URL}/api/v1/contacts?limit=20&offset=0`, { headers })
    check(contacts, { 'contacts 200/401': (r) => r.status === 200 || r.status === 401 })

    const costs = http.get(`${BASE_URL}/api/v1/costs/summary`, { headers })
    check(costs, { 'costs 200/401': (r) => r.status === 200 || r.status === 401 })
  })

  sleep(0.2)
