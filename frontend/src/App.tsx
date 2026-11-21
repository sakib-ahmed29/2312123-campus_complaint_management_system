import { useCallback, useEffect, useMemo, useState } from "react"
import type { FormEvent } from "react"

type Role = "user" | "admin"
type Status = "pending" | "in_progress" | "resolved" | "rejected"
type Complaint = { id: number; title: string; description: string; category: string; status: Status; admin_response: string | null; created_at: string; updated_at: string; owner_id: string | null }
type User = { id: string; email: string; name: string; role: Role; is_banned?: boolean; ban_reason?: string | null; created_at?: string }
type Group = { id: string; name: string; description: string; owner_id: string }
type Stats = { users: { total: number; admins: number; banned: number; new_last_7_days: number }; complaints: { total: number; new_last_7_days: number; by_status: Record<string, number> }; groups: { total: number; new_last_7_days: number } }

let accessToken = ""
let refreshing: Promise<boolean> | null = null
async function refreshAccess(): Promise<boolean> {
  if (!refreshing) refreshing = fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then(async r => { if (!r.ok) return false; const d = await r.json(); accessToken = d.access_token; return true })
    .catch(() => false).finally(() => { refreshing = null })
  return refreshing
}
async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set("Content-Type", "application/json")
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`)
  const response = await fetch(path, { ...options, headers, credentials: "include" })
  if (response.status === 401 && retry && await refreshAccess()) return api<T>(path, options, false)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json(); if (typeof body.detail === "string") message = body.detail } catch { /* fallback */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
const categories = ["academic", "hostel", "library", "cafeteria", "transport", "it_network", "other"]
const statuses: Status[] = ["pending", "in_progress", "resolved", "rejected"]
const label = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase())
const date = (s?: string) => s ? new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(s)) : "—"

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [booting, setBooting] = useState(true)
  const [mode, setMode] = useState<"login" | "signup">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("academic")
  const [nextStatus, setNextStatus] = useState<Status>("in_progress")
  const [adminResponse, setAdminResponse] = useState("")
  const [stats, setStats] = useState<Stats | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [groupName, setGroupName] = useState("")
  const [groupDescription, setGroupDescription] = useState("")
  const [tab, setTab] = useState<"complaints" | "admin" | "groups" | "profile">("complaints")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  const loadData = useCallback(async () => {
    if (!user) return
    try {
      const [items, teams] = await Promise.all([api<Complaint[]>("/api/v1/complaints"), api<Group[]>("/api/v1/groups")])
      setComplaints(items); setGroups(teams); setSelected(current => current && items.some(x => x.id === current) ? current : items[0]?.id ?? null)
      if (user.role === "admin") {
        const [s, u] = await Promise.all([api<Stats>("/api/v1/admin/stats"), api<User[]>("/api/v1/admin/users?limit=100")])
        setStats(s); setUsers(u)
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load dashboard") }
  }, [user])
  useEffect(() => {
    let alive = true
    refreshAccess().then(async ok => {
      if (ok) { try { const profile = await api<User>("/api/v1/users/me"); if (alive) setUser(profile) } catch { accessToken = "" } }
      if (alive) setBooting(false)
    })
    return () => { alive = false }
  }, [])
  useEffect(() => { if (user) void loadData() }, [user, loadData])

  const active = useMemo(() => complaints.find(x => x.id === selected) ?? null, [complaints, selected])
  async function authenticate(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("")
    try {
      if (mode === "signup") await api("/api/v1/auth/signup", { method: "POST", body: JSON.stringify({ email, name, password }) })
      const result = await fetch("/api/v1/auth/login", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) })
      const body = await result.json()
      if (!result.ok) throw new Error(body.detail || "Login failed")
      accessToken = body.access_token
      setUser(body.user); setPassword(""); setNotice("Welcome to CampusCare.")
    } catch (e) { setError(e instanceof Error ? e.message : "Authentication failed") }
    finally { setBusy(false) }
  }
  async function logout() {
    try { await api("/api/v1/auth/logout", { method: "POST" }) } catch { /* local logout still clears the UI */ }
    accessToken = ""; setUser(null); setComplaints([]); setGroups([]); setStats(null); setUsers([])
  }
  async function submitComplaint(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      await api("/api/v1/complaints", { method: "POST", body: JSON.stringify({ title, description, category }) })
      setTitle(""); setDescription(""); setNotice("Complaint submitted."); await loadData()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not submit complaint") }
    finally { setBusy(false) }
  }
  async function updateStatus(item: Complaint) {
    try {
      await api(`/api/v1/complaints/${item.id}/status`, { method: "PATCH", body: JSON.stringify({ status: nextStatus, admin_response: adminResponse || null }) })
      setNotice("Complaint status updated."); setAdminResponse(""); await loadData()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update status") }
  }
  async function removeComplaint(item: Complaint) {
    if (!window.confirm(`Delete complaint #${item.id}?`)) return
    try { await api(`/api/v1/complaints/${item.id}`, { method: "DELETE" }); setNotice("Complaint deleted."); await loadData() }
    catch (e) { setError(e instanceof Error ? e.message : "Could not delete complaint") }
  }
  async function moderateUser(target: User, action: "ban" | "unban" | "admin" | "user") {
    try {
      if (action === "ban") await api(`/api/v1/admin/users/${target.id}/ban`, { method: "POST", body: JSON.stringify({ reason: "Administrative moderation" }) })
      if (action === "unban") await api(`/api/v1/admin/users/${target.id}/unban`, { method: "POST" })
      if (action === "admin" || action === "user") await api(`/api/v1/admin/users/${target.id}/role`, { method: "PATCH", body: JSON.stringify({ role: action }) })
      setNotice("User updated."); await loadData()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update user") }
  }
  async function createGroup(e: FormEvent) {
    e.preventDefault()
    try { await api("/api/v1/groups", { method: "POST", body: JSON.stringify({ name: groupName, description: groupDescription }) }); setGroupName(""); setGroupDescription(""); await loadData(); setNotice("Group created.") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not create group") }
  }
  async function downloadCsv(kind: string) {
    try {
      const response = await fetch(`/api/v1/admin/export/${kind}`, { headers: { Authorization: `Bearer ${accessToken}` }, credentials: "include" })
      if (!response.ok) throw new Error("Export failed")
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a")
      a.href = url; a.download = `campuscare-${kind}.csv`; a.click(); URL.revokeObjectURL(url)
    } catch (e) { setError(e instanceof Error ? e.message : "Export failed") }
  }

  if (booting) return <main className="app-shell"><div className="empty-state">Restoring secure session…</div></main>
  if (!user) return <main className="app-shell"><header className="topbar"><a className="brand" href="/"><span className="brand-mark">CC</span><span><strong>CampusCare</strong><small>Complaint management</small></span></a></header><section className="hero"><div><p className="eyebrow">INDEPENDENT UNIVERSITY, BANGLADESH</p><h1>Make campus <em>better.</em></h1><p className="hero-copy">Sign in or create an account to report and follow campus issues.</p></div></section>{error && <div className="alert error-alert">{error}</div>}<section className="panel" style={{ maxWidth: 480, margin: "0 auto 50px" }}><div className="panel-heading"><div><p className="eyebrow">SECURE ACCESS</p><h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2></div></div><form onSubmit={authenticate} className="admin-tools">{mode === "signup" && <label>Your name<input required minLength={2} maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>}<label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label><label>Password<input type="password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} /></label><button className="button primary" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button></form><p className="muted" style={{ fontSize: 12 }}>{mode === "login" ? "New to CampusCare?" : "Already registered?"} <button className="refresh-link" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError("") }}>{mode === "login" ? "Create an account" : "Sign in"}</button></p></section></main>

  return <main className="app-shell">
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark">CC</span><span><strong>CampusCare</strong><small>Complaint management</small></span></a><div className="topbar-right"><span className="live-dot" /> Secure workspace <span className="student-chip">{user.role === "admin" ? "Administrator" : "Member"} · {user.name}</span><button className="button secondary small" onClick={() => void logout()}>Sign out</button></div></header>
    <section className="hero"><div><p className="eyebrow">INDEPENDENT UNIVERSITY, BANGLADESH</p><h1>Make campus <em>better.</em></h1><p className="hero-copy">Report an issue, follow its progress, and help improve everyday campus life.</p></div><div className="hero-symbol" aria-hidden="true"><span>✳</span><i>CC</i></div></section>
    {error && <div className="alert error-alert" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}{notice && <div className="alert success-alert" role="status">{notice}<button onClick={() => setNotice("")}>×</button></div>}
    <nav className="filters" style={{ display: "flex", flexWrap: "wrap" }}><button className="button secondary" onClick={() => setTab("complaints")}>My complaints</button><button className="button secondary" onClick={() => setTab("groups")}>Groups</button><button className="button secondary" onClick={() => setTab("profile")}>My profile</button>{user.role === "admin" && <button className="button primary" onClick={() => setTab("admin")}>Admin dashboard</button>}</nav>
    {tab === "complaints" && <>
      <section className="stats-grid"><article className="stat-card"><span className="stat-label">My complaints</span><strong>{complaints.length}</strong><small>Total submitted</small></article>{statuses.slice(0,3).map(s => <article className="stat-card" key={s}><span className="stat-label">{label(s)}</span><strong>{complaints.filter(x => x.status === s).length}</strong><small>Current status</small></article>)}</section>
      <div className="workspace"><section className="panel list-panel"><div className="panel-heading"><div><p className="eyebrow">YOUR CAMPUS FEEDBACK</p><h2>Complaints</h2></div><button className="button secondary small" onClick={() => void loadData()}>↻ Refresh</button></div><div className="complaint-list">{complaints.length ? complaints.map(item => <button className={`complaint-row ${selected === item.id ? "selected" : ""}`} key={item.id} onClick={() => { setSelected(item.id); setNextStatus(item.status === "pending" ? "in_progress" : "resolved") }}><span className="row-icon">{label(item.category).slice(0,1)}</span><span className="row-main"><strong>{item.title}</strong><small>#{item.id} · {label(item.category)} · {date(item.created_at)}</small></span><span className={`status-pill ${item.status}`}>{label(item.status)}</span></button>) : <div className="empty-state">No complaints submitted yet.</div>}</div></section><section className="panel detail-panel">{active ? <><div className="detail-heading"><div><p className="eyebrow">COMPLAINT #{active.id}</p><h2>{active.title}</h2></div><span className={`status-pill large ${active.status}`}>{label(active.status)}</span></div><div className="meta-line">{label(active.category)} · Submitted {date(active.created_at)}</div><div className="description-block"><h3>Description</h3><p>{active.description}</p></div>{active.admin_response && <div className="response-block"><h3>Administration response</h3><p>{active.admin_response}</p></div>}{active.status === "pending" && <button className="button danger-ghost" onClick={() => void removeComplaint(active)}>Delete pending complaint</button>}{user.role === "admin" && active.status !== "resolved" && active.status !== "rejected" && <div className="admin-tools"><h3>Moderate complaint</h3><label>New status<select value={nextStatus} onChange={e => setNextStatus(e.target.value as Status)}>{statuses.filter(s => s !== active.status).map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label><label>Response<textarea rows={2} value={adminResponse} onChange={e => setAdminResponse(e.target.value)} /></label><button className="button primary" onClick={() => void updateStatus(active)}>Save status</button></div>}</> : <div className="empty-detail"><h2>Select a complaint</h2></div>}</section></div>
      <section className="panel form-panel"><div className="panel-heading"><div><p className="eyebrow">HAVE SOMETHING TO REPORT?</p><h2>Submit a complaint</h2></div></div><form onSubmit={submitComplaint}><div className="form-grid"><label>Complaint title<input required minLength={5} maxLength={100} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Projector not working in room 302" /></label><label>Category<select value={category} onChange={e => setCategory(e.target.value)}>{categories.map(c => <option key={c} value={c}>{label(c)}</option>)}</select></label><label className="full-width">Describe the issue<textarea required minLength={10} maxLength={2000} rows={4} value={description} onChange={e => setDescription(e.target.value)} /></label></div><div className="form-footer"><p>New complaints start as Pending.</p><button className="button primary" disabled={busy}>{busy ? "Submitting…" : "Submit complaint →"}</button></div></form></section>
    </>}
    {tab === "admin" && user.role === "admin" && <><section className="stats-grid">{[["Users",stats?.users.total],["Banned",stats?.users.banned],["Complaints",stats?.complaints.total],["Groups",stats?.groups.total]].map(([k,v]) => <article className="stat-card" key={String(k)}><span className="stat-label">{k}</span><strong>{v ?? "…"}</strong><small>Last 7 days: {k === "Users" ? stats?.users.new_last_7_days ?? 0 : k === "Complaints" ? stats?.complaints.new_last_7_days ?? 0 : k === "Groups" ? stats?.groups.new_last_7_days ?? 0 : "—"}</small></article>)}</section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">ACCESS CONTROL</p><h2>User management</h2></div><button className="button secondary" onClick={() => void loadData()}>Refresh</button></div>{users.map(u => <div className="complaint-row" key={u.id}><span className="row-main"><strong>{u.name} · {u.email}</strong><small>{u.role} · {u.is_banned ? "Banned" : "Active"} · {u.id}</small></span>{u.id !== user.id && <><button className="button secondary small" onClick={() => void moderateUser(u, u.role === "admin" ? "user" : "admin")}>{u.role === "admin" ? "Make user" : "Make admin"}</button>{u.role !== "admin" && <button className="button danger-ghost small" onClick={() => void moderateUser(u, u.is_banned ? "unban" : "ban")}>{u.is_banned ? "Unban" : "Ban"}</button>}</>}</div>)}</section><section className="panel form-panel"><h2>Audit & exports</h2><div className="form-footer"><button className="button secondary" onClick={() => void downloadCsv("users")}>Export users CSV</button><button className="button secondary" onClick={() => void downloadCsv("complaints")}>Export complaints CSV</button><button className="button secondary" onClick={() => void downloadCsv("activity")}>Export activity CSV</button><a href="/api/v1/admin/audit" target="_blank" rel="noreferrer">Audit API ↗</a></div></section></>}
    {tab === "groups" && <><section className="panel"><div className="panel-heading"><div><p className="eyebrow">COLLABORATION</p><h2>Your groups</h2></div></div>{groups.map(g => <div className="complaint-row" key={g.id}><span className="row-main"><strong>{g.name}</strong><small>{g.description || "No description"} · Owner {g.owner_id === user.id ? "you" : g.owner_id}</small></span><button className="button secondary small" onClick={async () => { try { const rows = await api<unknown[]>(`/api/v1/groups/${g.id}/records`); setNotice(`Group has ${rows.length} shared records.`) } catch(e) { setError(e instanceof Error ? e.message : "Could not load group") } }}>View records</button>{g.owner_id === user.id && <button className="button danger-ghost small" onClick={async () => { if (confirm("Delete this group?")) { await api(`/api/v1/groups/${g.id}`, { method: "DELETE" }); await loadData() } }}>Delete</button>}</div>)}{!groups.length && <p className="muted">You are not a member of any groups yet.</p>}</section><section className="panel form-panel"><h2>Create a group</h2><form onSubmit={createGroup} className="admin-tools"><label>Group name<input required minLength={2} value={groupName} onChange={e => setGroupName(e.target.value)} /></label><label>Description<textarea value={groupDescription} onChange={e => setGroupDescription(e.target.value)} /></label><button className="button primary">Create group</button></form></section></>}
    {tab === "profile" && <ProfilePanel user={user} onUpdate={async n => { const p = await api<User>("/api/v1/users/me", { method: "PATCH", body: JSON.stringify({ name: n }) }); setUser(p); setNotice("Profile updated.") }} onPassword={async (a,b) => { await api("/api/v1/users/me/password", { method: "POST", body: JSON.stringify({ current_password: a, new_password: b }) }); accessToken = ""; setUser(null); setNotice("Password changed. Sign in again.") }} />}
    <footer><span>CampusCare · Secure multi-user platform</span><span>Independent University, Bangladesh</span><a href="/api/docs" target="_blank" rel="noreferrer">API documentation ↗</a></footer>
  </main>
}

function ProfilePanel({ user, onUpdate, onPassword }: { user: User; onUpdate: (name: string) => Promise<void>; onPassword: (a: string,b: string) => Promise<void> }) {
  const [name,setName]=useState(user.name); const [current,setCurrent]=useState(""); const [next,setNext]=useState(""); const [error,setError]=useState("")
  return <section className="panel form-panel"><p className="eyebrow">ACCOUNT SETTINGS</p><h2>My profile</h2><p>{user.email} · {user.role}</p><form className="admin-tools" onSubmit={async e=>{e.preventDefault();try{await onUpdate(name)}catch(x){setError(x instanceof Error?x.message:"Update failed")}}}><label>Display name<input value={name} onChange={e=>setName(e.target.value)} minLength={2} required /></label><button className="button primary">Save profile</button></form><div className="divider" /><h2>Change password</h2><form className="admin-tools" onSubmit={async e=>{e.preventDefault();try{await onPassword(current,next)}catch(x){setError(x instanceof Error?x.message:"Password update failed")}}}><label>Current password<input type="password" value={current} onChange={e=>setCurrent(e.target.value)} required /></label><label>New password<input type="password" minLength={8} value={next} onChange={e=>setNext(e.target.value)} required /></label><button className="button primary">Change password</button></form>{error && <p className="error-alert">{error}</p>}</section>
}
