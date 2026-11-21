import { useCallback, useEffect, useMemo, useState } from "react"
import type { FormEvent } from "react"

type Category = "academic" | "hostel" | "library" | "cafeteria" | "transport" | "it_network" | "other"
type Status = "pending" | "in_progress" | "resolved" | "rejected"
type Complaint = {
  id: number
  title: string
  description: string
  category: Category
  status: Status
  admin_response: string | null
  created_at: string
  updated_at: string
}
type ComplaintForm = { title: string; description: string; category: Category }

const categories: { value: Category; label: string }[] = [
  { value: "academic", label: "Academic" }, { value: "hostel", label: "Hostel" },
  { value: "library", label: "Library" }, { value: "cafeteria", label: "Cafeteria" },
  { value: "transport", label: "Transport" }, { value: "it_network", label: "IT & Network" },
  { value: "other", label: "Other" },
]
const statuses: { value: Status; label: string }[] = [
  { value: "pending", label: "Pending" }, { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" }, { value: "rejected", label: "Rejected" },
]
const emptyForm: ComplaintForm = { title: "", description: "", category: "academic" }

let accessToken = ""
let currentRole: "user" | "admin" = "user"

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
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
  return response.json() as Promise<T>
}

function labelForCategory(value: Category) {
  return categories.find((item) => item.value === value)?.label ?? value
}
function labelForStatus(value: Status) {
  return statuses.find((item) => item.value === value)?.label ?? value
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}

function ComplaintWorkspace() {
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState<ComplaintForm>(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [filterStatus, setFilterStatus] = useState("")
  const [filterCategory, setFilterCategory] = useState("")
  const [adminResponse, setAdminResponse] = useState("")
  const [nextStatus, setNextStatus] = useState<Status>("in_progress")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  const loadComplaints = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const params = new URLSearchParams()
      if (filterStatus) params.set("status", filterStatus)
      if (filterCategory) params.set("category", filterCategory)
      const data = await api<Complaint[]>(`/api/v1/complaints?${params.toString()}`)
      setComplaints(data)
      setSelected((current) => current && data.some((item) => item.id === current) ? current : data[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load complaints")
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterCategory])

  useEffect(() => { void loadComplaints() }, [loadComplaints])

  const activeComplaint = useMemo(
    () => complaints.find((item) => item.id === selected) ?? null,
    [complaints, selected],
  )
  useEffect(() => {
  if (!activeComplaint) return

  if (activeComplaint.status === "pending") {
    setNextStatus("in_progress")
  } else if (activeComplaint.status === "in_progress") {
    setNextStatus("resolved")
  }
}, [activeComplaint?.id, activeComplaint?.status])
  const counts = useMemo(() => ({
    total: complaints.length,
    pending: complaints.filter((item) => item.status === "pending").length,
    progress: complaints.filter((item) => item.status === "in_progress").length,
    resolved: complaints.filter((item) => item.status === "resolved").length,
  }), [complaints])

  function startCreate() {
    setEditingId(null); setForm(emptyForm); setNotice(""); setError("")
  }
  function startEdit(item: Complaint) {
    setEditingId(item.id)
    setForm({ title: item.title, description: item.description, category: item.category })
    setNotice(""); setError("")
  }
  async function submitComplaint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true); setError(""); setNotice("")
    try {
      const saved = await api<Complaint>(
        editingId ? `/api/v1/complaints/${editingId}` : "/api/v1/complaints",
        { method: editingId ? "PATCH" : "POST", body: JSON.stringify(form) },
      )
      setNotice(editingId ? "Complaint updated successfully." : "Complaint submitted successfully.")
      setEditingId(null); setForm(emptyForm)
      await loadComplaints()
      setSelected(saved.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save complaint")
    } finally { setSaving(false) }
  }
  async function removeComplaint(item: Complaint) {
    if (!window.confirm(`Delete complaint #${item.id}? This cannot be undone.`)) return
    setError(""); setNotice("")
    try {
      await api<void>(`/api/v1/complaints/${item.id}`, { method: "DELETE" })
      setNotice("Complaint deleted.")
      if (editingId === item.id) startCreate()
      await loadComplaints()
    } catch (err) { setError(err instanceof Error ? err.message : "Could not delete complaint") }
  }
  async function changeStatus(item: Complaint) {
    setError(""); setNotice("")
    try {
      await api<Complaint>(`/api/v1/complaints/${item.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus, admin_response: adminResponse || null }),
      })
      setNotice("Complaint status updated.")
      setAdminResponse("")
      await loadComplaints()
      setSelected(item.id)
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update status") }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="CampusCare home">
          <span className="brand-mark">CC</span>
          <span><strong>CampusCare</strong><small>Complaint management</small></span>
        </a>
        <div className="topbar-right"><span className="live-dot" /> MVP workspace <span className="student-chip">Student portal</span></div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">INDEPENDENT UNIVERSITY, BANGLADESH</p>
          <h1>Make campus <em>better.</em></h1>
          <p className="hero-copy">Report an issue, follow its progress, and help improve everyday campus life.</p>
        </div>
        <div className="hero-symbol" aria-hidden="true"><span>✳</span><i>CC</i></div>
      </section>

      <section className="stats-grid" aria-label="Complaint summary">
        <article className="stat-card"><span className="stat-label">Showing</span><strong>{counts.total}</strong><small>Complaints</small></article>
        <article className="stat-card"><span className="stat-label">Awaiting review</span><strong>{counts.pending}</strong><small>Pending</small></article>
        <article className="stat-card"><span className="stat-label">Being handled</span><strong>{counts.progress}</strong><small>In progress</small></article>
        <article className="stat-card"><span className="stat-label">Completed</span><strong>{counts.resolved}</strong><small>Resolved</small></article>
      </section>

      {(error || notice) && <div className={error ? "alert error-alert" : "alert success-alert"} role="status">{error || notice}<button onClick={() => { setError(""); setNotice("") }} aria-label="Dismiss">×</button></div>}

      <div className="workspace">
        <section className="panel list-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">CAMPUS FEEDBACK</p><h2>Complaints</h2></div>
            <button className="button primary small" onClick={startCreate}>＋ New complaint</button>
          </div>
          <div className="filters">
            <label>Category<select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}><option value="">All categories</option>{categories.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label>Status<select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}><option value="">All statuses</option>{statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
          </div>
          <div className="complaint-list">
            {loading ? <div className="empty-state">Loading complaints…</div> : complaints.length === 0 ? <div className="empty-state"><span>☷</span><strong>No complaints found</strong><p>Try another filter or submit a new complaint.</p></div> :
              complaints.map((item) => <button className={`complaint-row ${selected === item.id ? "selected" : ""}`} key={item.id} onClick={() => { setSelected(item.id); setAdminResponse("") }}>
                <span className="row-icon">{labelForCategory(item.category).slice(0, 1)}</span>
                <span className="row-main"><strong>{item.title}</strong><small>#{item.id} · {labelForCategory(item.category)} · {formatDate(item.created_at)}</small></span>
                <span className={`status-pill ${item.status}`}>{labelForStatus(item.status)}</span>
              </button>)
            }
          </div>
          <button className="refresh-link" onClick={() => void loadComplaints()}>↻ Refresh list</button>
        </section>

        <section className="panel detail-panel">
          {activeComplaint ? <>
            <div className="detail-heading"><div><p className="eyebrow">COMPLAINT #{activeComplaint.id}</p><h2>{activeComplaint.title}</h2></div><span className={`status-pill large ${activeComplaint.status}`}>{labelForStatus(activeComplaint.status)}</span></div>
            <div className="meta-line"><span>{labelForCategory(activeComplaint.category)}</span><span>Submitted {formatDate(activeComplaint.created_at)}</span></div>
            <div className="description-block"><h3>Description</h3><p>{activeComplaint.description}</p></div>
            {activeComplaint.admin_response && <div className="response-block"><h3>Administration response</h3><p>{activeComplaint.admin_response}</p></div>}
            <div className="detail-actions">
              {activeComplaint.status === "pending" && <><button className="button secondary" onClick={() => startEdit(activeComplaint)}>Edit complaint</button><button className="button danger-ghost" onClick={() => void removeComplaint(activeComplaint)}>Delete</button></>}
            </div>
            {currentRole === "admin" && (activeComplaint.status === "pending" || activeComplaint.status === "in_progress") ? <div className="admin-tools">
              <div><p className="eyebrow">DEMO STATUS CONTROL</p><h3>Update progress</h3><p className="muted">For assessment demonstration of the status-update API.</p></div>
              <label>New status<select value={nextStatus} onChange={(e) => setNextStatus(e.target.value as Status)}>{statuses.filter((s) => s.value !== activeComplaint.status && (activeComplaint.status === "pending" ? ["in_progress", "rejected"].includes(s.value) : ["resolved", "rejected"].includes(s.value))).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
              <label>Admin response <textarea value={adminResponse} onChange={(e) => setAdminResponse(e.target.value)} rows={2} placeholder="Optional response to the student" /></label>
              <button className="button primary" onClick={() => void changeStatus(activeComplaint)}>Save status update</button>
            </div> : null}
          </> : <div className="empty-detail"><span>✳</span><h2>Select a complaint</h2><p>Choose an item from the list to view its details and available actions.</p></div>}
        </section>
      </div>

      <section className="panel form-panel">
        <div className="panel-heading"><div><p className="eyebrow">{editingId ? `EDIT COMPLAINT #${editingId}` : "HAVE SOMETHING TO REPORT?"}</p><h2>{editingId ? "Update your complaint" : "Submit a complaint"}</h2></div><span className="form-step">01 / 01</span></div>
        <form onSubmit={submitComplaint}>
          <div className="form-grid">
            <label>Complaint title<input required minLength={5} maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Projector not working in room 302" /></label>
            <label>Category<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as Category })}>{categories.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="full-width">Describe the issue<textarea required minLength={10} maxLength={2000} rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Share what happened, where it happened, and any details that may help…" /></label>
          </div>
          <div className="form-footer"><p>Your complaint will be created with <strong>Pending</strong> status.</p><div>{editingId && <button type="button" className="button secondary" onClick={startCreate}>Cancel edit</button>}<button className="button primary" type="submit" disabled={saving}>{saving ? "Saving…" : editingId ? "Save changes →" : "Submit complaint →"}</button></div></div>
        </form>
      </section>
      <footer><span>CampusCare · MVP demonstration</span><span>Built for Independent University, Bangladesh</span><a href="/api/docs" target="_blank" rel="noreferrer">API documentation ↗</a></footer>
    </main>
  )
}


function AdminDashboard() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [users, setUsers] = useState<Array<{id:number;email:string;full_name:string;role:string;is_banned:boolean}>>([])
  const [activity, setActivity] = useState<Array<{id:number;event:string;user_id:number|null;created_at:string;detail:string|null}>>([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState("Policy violation")
  const [query, setQuery] = useState("")
  async function load() {
    setBusy(true); setError("")
    try {
      const [s, u, a] = await Promise.all([
        api<Record<string,number>>("/api/v1/admin/stats"),
        api<typeof users>(`/api/v1/admin/users?q=${encodeURIComponent(query)}&limit=50`),
        api<typeof activity>("/api/v1/admin/activity?limit=30"),
      ])
      setStats(s); setUsers(u); setActivity(a)
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load admin data") }
    finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [])
  async function act(userId:number, action:"ban"|"unban"|"promote") {
    try {
      if(action==="ban") await api(`/api/v1/admin/users/${userId}/ban`, {method:"POST",body:JSON.stringify({reason})})
      if(action==="unban") await api(`/api/v1/admin/users/${userId}/unban`, {method:"POST"})
      if(action==="promote") await api(`/api/v1/admin/users/${userId}/role`, {method:"PATCH",body:JSON.stringify({role:"admin"})})
      await load()
    } catch(e) { setError(e instanceof Error ? e.message : "Action failed") }
  }
  return <section style={{maxWidth:1100,margin:"24px auto",padding:"24px",background:"#fff",borderRadius:18}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap"}}>
      <div><p className="eyebrow">CAMPUSCARE CONTROL CENTER</p><h2>Admin dashboard</h2></div>
      <button className="button secondary" onClick={()=>void load()} disabled={busy}>{busy?"Loading…":"Refresh dashboard"}</button>
    </div>
    {error && <p role="alert" style={{color:"#b42318"}}>{error}</p>}
    {stats && <div className="stats-grid">{Object.entries(stats).map(([k,v])=><article className="stat-card" key={k}><span className="stat-label">{k.replaceAll("_"," ")}</span><strong>{v}</strong></article>)}</div>}
    <h3 style={{marginTop:28}}>User management</h3>
    <div style={{display:"flex",gap:8,marginBottom:12}}><input aria-label="Search users" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search name or email"/><button className="button secondary" onClick={()=>void load()}>Search</button></div>
    <label>Reason for ban <input value={reason} onChange={e=>setReason(e.target.value)} /></label>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>ID</th><th>User</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {users.map(u=><tr key={u.id}><td>{u.id}</td><td>{u.full_name}<br/><small>{u.email}</small></td><td>{u.role}</td><td>{u.is_banned?"Banned":"Active"}</td><td style={{display:"flex",gap:6,flexWrap:"wrap"}}>{u.role==="user" && <button className="button secondary" onClick={()=>void act(u.id,"promote")}>Make admin</button>}{u.role==="user" && (u.is_banned?<button className="button secondary" onClick={()=>void act(u.id,"unban")}>Unban</button>:<button className="button danger-ghost" onClick={()=>void act(u.id,"ban")}>Ban</button>)}</td></tr>)}
    </tbody></table></div>
    <h3 style={{marginTop:28}}>Recent activity</h3>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Event</th><th>User ID</th><th>Details</th><th>Time</th></tr></thead><tbody>{activity.map(a=><tr key={a.id}><td>{a.event}</td><td>{a.user_id??"—"}</td><td>{a.detail??"—"}</td><td>{new Date(a.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>
    <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:18}}>{["users","records","activity"].map(k=><a key={k} className="button secondary" href={`/api/v1/admin/export/${k}`} onClick={async e=>{e.preventDefault();try{const data=await api<string>(`/api/v1/admin/export/${k}`);const blob=new Blob([data],{type:"text/csv"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`campuscare-${k}.csv`;link.click();URL.revokeObjectURL(url)}catch(err){setError(err instanceof Error?err.message:"Export failed")}}}>Export {k} CSV</a>)}</div>
  </section>
}

export default function App() {
  const [restoring, setRestoring] = useState(true)
  const [user, setUser] = useState<{id:number;email:string;full_name:string;role:"user"|"admin"}|null>(null)
  const [mode, setMode] = useState<"login"|"signup">("login")
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [adminView, setAdminView] = useState(false)
  useEffect(() => {
    let alive = true
    fetch("/api/v1/auth/refresh",{method:"POST",credentials:"include"}).then(async r=>{
      if(!r.ok) return null
      return r.json()
    }).then(async tokens=>{
      if(!tokens || !alive) return
      accessToken=tokens.access_token
      const me=await api<{id:number;email:string;full_name:string;role:"user"|"admin"}>("/api/v1/users/me")
      if(alive){currentRole=me.role;setUser(me)}
    }).catch(()=>{}).finally(()=>{if(alive)setRestoring(false)})
    const expired=()=>{if(alive){accessToken="";currentRole="user";setUser(null);setError("Your session expired. Please sign in again.")}}
    window.addEventListener("campuscare:session-expired",expired)
    return ()=>{alive=false;window.removeEventListener("campuscare:session-expired",expired)}
  },[])
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();setBusy(true);setError("")
    try {
      if(mode==="signup") await api("/api/v1/auth/signup",{method:"POST",body:JSON.stringify({email,full_name:name,password})})
      const tokens=await api<{access_token:string;user:{id:number;email:string;full_name:string;role:"user"|"admin"}}>("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})})
      accessToken=tokens.access_token;currentRole=tokens.user.role;setUser(tokens.user)
    } catch(err) {setError(err instanceof Error?err.message:"Authentication failed")}
    finally {setBusy(false)}
  }
  async function signOut() {
    try {await api("/api/v1/auth/logout",{method:"POST"})} catch {}
    accessToken="";currentRole="user";setUser(null);setAdminView(false)
  }
  if(restoring) return <main className="app-shell"><div className="panel" style={{margin:"12vh auto",maxWidth:480,padding:32}}>Restoring secure session…</div></main>
  if(!user) return <main className="app-shell"><section className="panel" style={{maxWidth:480,margin:"8vh auto",padding:32}}>
    <p className="eyebrow">INDEPENDENT UNIVERSITY, BANGLADESH</p><h1>Welcome to <em>CampusCare.</em></h1><p className="muted">Sign in to manage your campus complaints securely.</p>
    {error&&<p role="alert" style={{color:"#b42318"}}>{error}</p>}
    <form onSubmit={submit} style={{display:"grid",gap:14}}>
      {mode==="signup"&&<label>Full name<input required minLength={2} value={name} onChange={e=>setName(e.target.value)} /></label>}
      <label>Email<input type="email" required value={email} onChange={e=>setEmail(e.target.value)} /></label>
      <label>Password<input type="password" required minLength={8} value={password} onChange={e=>setPassword(e.target.value)} /></label>
      <button className="button primary" disabled={busy}>{busy?"Please wait…":mode==="login"?"Sign in":"Create account"}</button>
    </form>
    <p style={{marginTop:18}}>{mode==="login"?"New to CampusCare?":"Already registered?"} <button className="refresh-link" onClick={()=>{setMode(mode==="login"?"signup":"login");setError("")}}>{mode==="login"?"Create an account":"Sign in"}</button></p>
  </section></main>
  return <><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,padding:"12px max(20px,calc((100% - 1180px)/2))",background:"#102b26",color:"#fff"}}>
    <span>Signed in as <strong>{user.full_name}</strong> · {user.role}</span><div style={{display:"flex",gap:8}}>{user.role==="admin"&&<button className="button secondary" onClick={()=>setAdminView(!adminView)}>{adminView?"Complaint workspace":"Admin dashboard"}</button>}<button className="button secondary" onClick={()=>void signOut()}>Sign out</button></div>
  </div>{adminView&&user.role==="admin"?<AdminDashboard/>:<ComplaintWorkspace/>}</>
}
