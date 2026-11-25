const TOKEN_KEY = 'hms_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY))

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) {
    payload = new URLSearchParams(form)
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('hms-logout'))
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : j.detail?.map((d) => `${d.loc?.slice(-1)}: ${d.msg}`).join('; ') || msg
    } catch { /* non-JSON error */ }
    throw new ApiError(res.status, msg)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  get: (p) => request(p),
  post: (p, body = {}) => request(p, { method: 'POST', body }),
  put: (p, body) => request(p, { method: 'PUT', body }),
  patch: (p, body) => request(p, { method: 'PATCH', body }),
  del: (p) => request(p, { method: 'DELETE' }),
  login: (username, password) => request('/auth/login', { method: 'POST', form: { username, password } }),
}
