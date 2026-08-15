import { useState } from 'react'
import { supportChat } from '../../lib/api'

interface SupportChatProps {
  customerEmail: string
}

export function SupportChat({ customerEmail }: SupportChatProps) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [awaitingCode, setAwaitingCode] = useState(false)
  const [history, setHistory] = useState<{ role: 'user' | 'bot'; text: string }[]>([])
  const [loading, setLoading] = useState(false)

  const send = async (overrideMessage?: string, overrideCode?: string) => {
    const text = overrideMessage ?? message
    if (!text.trim()) return
    setHistory((h) => [...h, { role: 'user', text }])
    setMessage('')
    setLoading(true)
    try {
      const res = await supportChat(text, customerEmail, overrideCode || undefined)
      setHistory((h) => [...h, { role: 'bot', text: res.reply }])
      if (res.action_taken === 'verification_required') setAwaitingCode(true)
      if (res.action_taken !== 'verification_required') setAwaitingCode(false)
    } catch {
      setHistory((h) => [...h, { role: 'bot', text: 'ขออภัย ระบบขัดข้องชั่วคราว' }])
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 rounded-full bg-blue-600 px-4 py-2 text-white shadow-lg"
        aria-label="Support chat"
      >
        Support
      </button>
    )
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex h-96 w-80 flex-col rounded-xl border bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="font-semibold">Support</span>
        <button onClick={() => setOpen(false)} aria-label="Close" className="text-gray-500">×</button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {history.map((h, i) => (
          <div key={i} className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${h.role === 'user' ? 'ml-auto bg-blue-600 text-white' : 'bg-gray-100'}`}>
            {h.text}
          </div>
        ))}
        {loading && <div className="text-sm text-gray-400">…</div>}
      </div>
      <form
        onSubmit={(e) => { e.preventDefault(); awaitingCode ? send(message, verificationCode) : send(message) }}
        className="flex flex-col gap-2 border-t p-2"
      >
        {awaitingCode && (
          <input
            value={verificationCode}
            onChange={(e) => setVerificationCode(e.target.value)}
            placeholder="รหัสยืนยัน 6 หลัก"
            className="rounded border px-2 py-1 text-sm"
            maxLength={6}
          />
        )}
        <div className="flex gap-2">
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="พิมพ์ข้อความ..."
            className="flex-1 rounded border px-2 py-1 text-sm"
          />
          <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">ส่ง</button>
        </div>
      </form>
    </div>
  )
}
