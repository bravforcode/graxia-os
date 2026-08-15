import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SupportChat } from '../src/components/chat/SupportChat'

vi.mock('../src/lib/api', () => ({
  supportChat: vi.fn().mockResolvedValue({ intent: 'wismo', reply: 'สถานะออเดอร์: paid', action_taken: 'wismo' }),
}))

describe('SupportChat', () => {
  it('sends a message and shows the reply', async () => {
    render(<SupportChat customerEmail="test@example.com" />)
    fireEvent.click(screen.getByRole('button', { name: /support|help/i }))
    const input = screen.getByPlaceholderText(/พิมพ์ข้อความ/i)
    fireEvent.change(input, { target: { value: 'where is my order?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => {
      expect(screen.getByText(/สถานะออเดอร์/i)).toBeTruthy()
    })
  })

  it('shows a code input when verification is required', async () => {
    const { supportChat } = await import('../src/lib/api')
    vi.mocked(supportChat).mockResolvedValueOnce({
      intent: 'wismo',
      reply: 'เราส่งรหัสยืนยัน 6 หลักไปที่อีเมลของคุณแล้ว',
      action_taken: 'verification_required',
    })
    render(<SupportChat customerEmail="test@example.com" />)
    fireEvent.click(screen.getByRole('button', { name: /support|help/i }))
    const input = screen.getByPlaceholderText(/พิมพ์ข้อความ/i)
    fireEvent.change(input, { target: { value: 'where is my order?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/รหัสยืนยัน/i)).toBeTruthy()
    })
  })
})
