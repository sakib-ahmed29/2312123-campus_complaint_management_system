/** Same-origin API client. Access tokens are memory-only; refresh tokens remain in httpOnly cookies. */
let accessToken = ""
export let currentRole: "user" | "admin" = "user"

export function setAccessToken(token: string) { accessToken = token }
export function setCurrentRole(role: "user" | "admin") { currentRole = role }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const send = () => fetch(path, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...options.headers },
  })
  let response = await send()
  if (response.status === 401 && accessToken && !path.includes("/auth/refresh") && !path.includes("/auth/login")) {
    const refreshed = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    if (refreshed.ok) {
      const tokens = await refreshed.json()
      accessToken = tokens.access_token
      response = await send()
    } else {
      accessToken = ""
      window.dispatchEvent(new Event("campuscare:session-expired"))
    }
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = typeof body.detail === "string" ? body.detail : message
    } catch { /* use fallback message */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("text/csv") || contentType.startsWith("text/")) return await response.text() as T
  return response.json() as Promise<T>
}

