import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, getRuntimeHealthUrl } from '@/lib/api'

describe('runtime availability probe', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('targets the real API health route for relative API deployments', () => {
    expect(getRuntimeHealthUrl('/api/v1')).toBe(`${window.location.origin}/api/v1/system/health`)
  })

  it('preserves absolute API origins and prefixes', () => {
    expect(getRuntimeHealthUrl('https://api.bravos.ai/api/v1')).toBe(
      'https://api.bravos.ai/api/v1/system/health',
    )
  })

  it('does not treat an SPA fallback response as a healthy backend', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({
      data: '<!doctype html><div id="root"></div>',
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'text/html' },
      config: {},
    } as never)

    const result = await api.getRuntimeAvailability()

    expect(result.available).toBe(false)
    expect(result.checkedUrl).toMatch(/\/api\/v1\/system\/health$/)
    expect(result.message).toContain('SPA fallback')
  })
})
