import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { getToken } from './api'

const Ctx = createContext({ subscribe: () => () => {}, status: 'offline' })
export const useLive = () => useContext(Ctx)

let toastId = 0

/**
 * One WebSocket per session. Change events ("er", "surgery", …) trigger refetches through the
 * normal REST endpoints; alerts become toasts. Reconnects with backoff and resyncs everything.
 */
export function LiveProvider({ children }) {
  const listeners = useRef(new Set())
  const [status, setStatus] = useState('connecting')
  const [toasts, setToasts] = useState([])

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  useEffect(() => {
    let ws, retryTimer, pingTimer, attempt = 0, closed = false, hadConnection = false
    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${window.location.host}/api/ws`)
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: getToken() }))
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'hello') {
          setStatus('live')
          attempt = 0
          if (hadConnection) listeners.current.forEach((fn) => fn(['*'])) // missed events while offline: resync
          hadConnection = true
        } else if (msg.type === 'event') {
          listeners.current.forEach((fn) => fn(msg.topics))
        } else if (msg.type === 'alert') {
          const id = ++toastId
          setToasts((t) => [...t.slice(-4), { id, ...msg }])
          if (msg.level !== 'critical') setTimeout(() => dismiss(id), 9000)
        }
      }
      ws.onclose = (ev) => {
        setStatus('offline')
        clearInterval(pingTimer)
        if (!closed && ev.code !== 4401) retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000))
      }
      pingTimer = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    }
    connect()
    return () => { closed = true; clearTimeout(retryTimer); clearInterval(pingTimer); ws && ws.close() }
  }, [dismiss])

  return (
    <Ctx.Provider value={{ subscribe, status }}>
      {children}
      <div className="toasts" aria-live="assertive">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.level}`} role="alert">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <b>{t.title}</b>
              <button className="btn ghost sm" onClick={() => dismiss(t.id)} aria-label="Dismiss">✕</button>
            </div>
            <div className="small">{t.message}</div>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
