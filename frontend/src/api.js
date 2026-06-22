// Fetch wrapper for the Manufacturing Agent API.
// Base URL comes from VITE_API_BASE, defaulting to http://localhost:8000.
const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(status, detail, message) {
    super(message || detail || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    // Network / CORS failure.
    throw new ApiError(0, 'network_error', '서버에 연결할 수 없습니다.')
  }

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    throw new ApiError(res.status, detail)
  }
  return data
}

export const api = {
  base: BASE,

  createUser: () => request('/users', { method: 'POST', body: {} }),

  deleteUser: (userId) => request(`/users/${userId}`, { method: 'DELETE' }),

  listThreads: (userId) => request(`/users/${userId}/threads`),

  createThread: (userId, title) =>
    request(`/users/${userId}/threads`, {
      method: 'POST',
      body: title ? { title } : {},
    }),

  deleteThread: (userId, threadId) =>
    request(`/users/${userId}/threads/${threadId}`, { method: 'DELETE' }),

  getHistory: (userId, threadId) =>
    request(`/users/${userId}/threads/${threadId}/history`),

  chat: ({ userId, threadId, message, inputFeatures, debug }) =>
    request(`/chat?debug=${debug ? 'true' : 'false'}`, {
      method: 'POST',
      body: {
        user_id: userId,
        thread_id: threadId,
        message,
        ...(inputFeatures ? { input_features: inputFeatures } : {}),
      },
    }),

  resume: ({ userId, threadId }) =>
    request('/chat/resume', {
      method: 'POST',
      body: { user_id: userId, thread_id: threadId },
    }),

  getUsage: () => request('/usage'),
}

// Stream chat answers via Server-Sent Events.
//
// EventSource cannot issue POST requests, so we use fetch() + a ReadableStream
// reader and parse the SSE frames manually: the body is a sequence of events
// separated by a blank line ("\n\n"); within each event, lines beginning with
// "data: " carry the JSON payload. We accumulate decoded bytes in `buf`, split
// on "\n\n", parse each complete frame's data line(s), and dispatch by `type`.
export async function chatStream(
  body,
  { debug = false, onStep, onStart, onDone, onError, signal } = {}
) {
  let res
  try {
    res = await fetch(`${BASE}/chat/stream?debug=${debug ? 'true' : 'false'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if (e && e.name === 'AbortError') return
    onError?.({ status: 0, code: 'network', message: '서버에 연결할 수 없습니다.' })
    return
  }

  if (!res.ok || !res.body) {
    let detail = null
    try {
      const text = await res.text()
      if (text) {
        try {
          const j = JSON.parse(text)
          detail = j && typeof j === 'object' ? j.detail : text
        } catch {
          detail = text
        }
      }
    } catch {
      /* ignore */
    }
    onError?.({ status: res.status, code: detail, message: detail })
    return
  }

  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''

  const dispatch = (frame) => {
    // A frame may contain one or more "data: ..." lines.
    const dataLines = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(line.startsWith('data: ') ? 6 : 5))
      }
    }
    if (dataLines.length === 0) return
    let evt
    try {
      evt = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }
    switch (evt.type) {
      case 'start':
        onStart?.(evt)
        break
      case 'step':
        onStep?.(evt)
        break
      case 'done':
        onDone?.(evt)
        break
      case 'error':
        onError?.({ status: null, code: evt.code, message: evt.message })
        break
      default:
        break
    }
  }

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        if (frame.trim()) dispatch(frame)
      }
    }
    // Flush any trailing frame without a terminating blank line.
    buf += dec.decode()
    if (buf.trim()) dispatch(buf)
  } catch (e) {
    if (e && e.name === 'AbortError') return
    onError?.({ status: 0, code: 'stream', message: '스트리밍 중 오류가 발생했습니다.' })
  }
}
