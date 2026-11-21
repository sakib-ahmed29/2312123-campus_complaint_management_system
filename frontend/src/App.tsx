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
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("text/csv") || contentType.startsWith("text/")) return await response.text() as T
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

      {currentRole === "user" && <section className="panel form-panel">
        <div className="panel-heading"><div><p className="eyebrow">{editingId ? `EDIT COMPLAINT #${editingId}` : "HAVE SOMETHING TO REPORT?"}</p><h2>{editingId ? "Update your complaint" : "Submit a complaint"}</h2></div><span className="form-step">01 / 01</span></div>
        <form onSubmit={submitComplaint}>
          <div className="form-grid">
            <label>Complaint title<input required minLength={5} maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Projector not working in room 302" /></label>
            <label>Category<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as Category })}>{categories.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="full-width">Describe the issue<textarea required minLength={10} maxLength={2000} rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Share what happened, where it happened, and any details that may help…" /></label>
          </div>
          <div className="form-footer"><p>Your complaint will be created with <strong>Pending</strong> status.</p><div>{editingId && <button type="button" className="button secondary" onClick={startCreate}>Cancel edit</button>}<button className="button primary" type="submit" disabled={saving}>{saving ? "Saving…" : editingId ? "Save changes →" : "Submit complaint →"}</button></div></div>
        </form>
      </section>}
      <footer><span>CampusCare · Secure workspace</span><span>Built for Independent University, Bangladesh</span><a href="/api/docs" target="_blank" rel="noreferrer">API documentation ↗</a></footer>
    </main>
  )
}


function AdminDashboard() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [users, setUsers] = useState<Array<{id:number;email:string;full_name:string;role:string;is_banned:boolean}>>([])
  const [activity, setActivity] = useState<Array<{id:number;event:string;user_id:number|null;created_at:string;detail:string|null}>>([])
  const [records,setRecords]=useState<Array<{id:number;title:string;category:string;status:string;owner_id:number|null}>>([])
  const [groups,setGroups]=useState<Array<{id:number;name:string;owner_id:number}>>([])
  const [security,setSecurity]=useState<{failed_logins_last_7_days:number;by_ip:Record<string,number>;by_account:Record<string,number>}|null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState("Policy violation")
  const [query, setQuery] = useState("")
  async function load() {
    setBusy(true); setError("")
    try {
      const [s, u, a, r, g, sec] = await Promise.all([
        api<Record<string,number>>("/api/v1/admin/stats"),
        api<typeof users>(`/api/v1/admin/users?q=${encodeURIComponent(query)}&limit=50`),
        api<typeof activity>("/api/v1/admin/activity?limit=30"),
        api<typeof records>("/api/v1/admin/records?limit=100"),
        api<typeof groups>("/api/v1/admin/groups"),
        api<typeof security>("/api/v1/admin/security"),
      ])
      setStats(s); setUsers(u); setActivity(a); setRecords(r); setGroups(g); setSecurity(sec)
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
    <h3 style={{marginTop:28}}>Content moderation</h3>
    <h4>Complaints</h4>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>ID</th><th>Title</th><th>Category</th><th>Status</th><th>Action</th></tr></thead><tbody>{records.map(r=><tr key={r.id}><td>{r.id}</td><td>{r.title}</td><td>{r.category}</td><td>{r.status}</td><td><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this complaint permanently?")){try{await api(`/api/v1/admin/records/${r.id}`,{method:"DELETE"});await load()}catch(e){setError(e instanceof Error?e.message:"Delete failed")}}}}>Delete</button></td></tr>)}</tbody></table></div>
    <h4 style={{marginTop:20}}>Shared groups</h4>
    {groups.map(g=><div key={g.id} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid #eee"}}><span>{g.name} · owner #{g.owner_id}</span><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this group and its shared records?")){try{await api(`/api/v1/admin/groups/${g.id}`,{method:"DELETE"});await load()}catch(e){setError(e instanceof Error?e.message:"Delete failed")}}}}>Delete group</button></div>)}
    <h3 style={{marginTop:28}}>Security monitoring</h3>
    {security&&<><p>Failed logins in last 7 days: <strong>{security.failed_logins_last_7_days}</strong></p><p>By IP: {Object.entries(security.by_ip).map(([ip,n])=>`${ip} (${n})`).join(", ")||"No failed logins"}</p><p>By account: {Object.entries(security.by_account).map(([email,n])=>`${email} (${n})`).join(", ")||"No failed logins"}</p></>}
    <h3 style={{marginTop:28}}>Recent activity</h3>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Event</th><th>User ID</th><th>Details</th><th>Time</th></tr></thead><tbody>{activity.map(a=><tr key={a.id}><td>{a.event}</td><td>{a.user_id??"—"}</td><td>{a.detail??"—"}</td><td>{new Date(a.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>
    <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:18}}>{["users","records","activity"].map(k=><a key={k} className="button secondary" href={`/api/v1/admin/export/${k}`} onClick={async e=>{e.preventDefault();try{const data=await api<string>(`/api/v1/admin/export/${k}`);const blob=new Blob([data],{type:"text/csv"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`campuscare-${k}.csv`;link.click();URL.revokeObjectURL(url)}catch(err){setError(err instanceof Error?err.message:"Export failed")}}}>Export {k} CSV</a>)}</div>
  </section>
}


function WorkspaceTools() {
  const [groups,setGroups]=useState<Array<{id:number;name:string;owner_id:number}>>([])
  const [selected,setSelected]=useState<number|null>(null)
  const [members,setMembers]=useState<Array<{user_id:number;can_create:boolean;can_edit:boolean;can_assign:boolean;is_owner:boolean}>>([])
  const [records,setRecords]=useState<Array<{id:number;title:string;body:string;assignee_id:number|null}>>([])
  const [groupName,setGroupName]=useState("")
  const [memberId,setMemberId]=useState("")
  const [permissions,setPermissions]=useState({can_create:false,can_edit:false,can_assign:false})
  const [recordTitle,setRecordTitle]=useState("")
  const [recordBody,setRecordBody]=useState("")
  const [profile,setProfile]=useState<{id:number;email:string;full_name:string}|null>(null)
  const [newEmail,setNewEmail]=useState("")
  const [newName,setNewName]=useState("")
  const [currentPassword,setCurrentPassword]=useState("")
  const [newPassword,setNewPassword]=useState("")
  const [sessions,setSessions]=useState<Array<{id:number;created_at:string;expires_at:string;ip_address:string|null}>>([])
  const [message,setMessage]=useState("")
  const [error,setError]=useState("")
  async function loadGroups(){
    try{const data=await api<typeof groups>("/api/v1/groups");setGroups(data);if(selected===null&&data.length)setSelected(data[0].id)}
    catch(e){setError(e instanceof Error?e.message:"Could not load groups")}
  }
  async function loadSelected(id:number){
    setSelected(id);setError("")
    try{const [m,r]=await Promise.all([api<typeof members>(`/api/v1/groups/${id}/members`),api<typeof records>(`/api/v1/groups/${id}/records`)]);setMembers(m);setRecords(r)}
    catch(e){setError(e instanceof Error?e.message:"Could not load group")}
  }
  useEffect(()=>{
    void loadGroups()
    api<{id:number;email:string;full_name:string}>("/api/v1/users/me").then(p=>{setProfile(p);setNewEmail(p.email);setNewName(p.full_name)}).catch(()=>{})
    api<typeof sessions>("/api/v1/auth/sessions").then(setSessions).catch(()=>{})
  },[])
  useEffect(()=>{if(selected!==null)void loadSelected(selected)},[selected])
  async function createGroup(e:FormEvent){e.preventDefault();try{await api("/api/v1/groups",{method:"POST",body:JSON.stringify({name:groupName})});setGroupName("");await loadGroups();setMessage("Group created.")}catch(x){setError(x instanceof Error?x.message:"Could not create group")}}
  async function addMember(e:FormEvent){e.preventDefault();if(selected===null)return;try{await api(`/api/v1/groups/${selected}/members`,{method:"POST",body:JSON.stringify({user_id:Number(memberId),...permissions})});setMemberId("");await loadSelected(selected);setMessage("Member permissions saved.")}catch(x){setError(x instanceof Error?x.message:"Could not add member")}}
  async function addRecord(e:FormEvent){e.preventDefault();if(selected===null)return;try{await api(`/api/v1/groups/${selected}/records`,{method:"POST",body:JSON.stringify({title:recordTitle,body:recordBody})});setRecordTitle("");setRecordBody("");await loadSelected(selected);setMessage("Shared record created.")}catch(x){setError(x instanceof Error?x.message:"Could not create record")}}
  async function saveProfile(e:FormEvent){e.preventDefault();try{const p=await api<typeof profile>("/api/v1/users/me",{method:"PATCH",body:JSON.stringify({email:newEmail,full_name:newName})});setProfile(p);setMessage("Profile updated.")}catch(x){setError(x instanceof Error?x.message:"Could not update profile")}}
  async function changePassword(e:FormEvent){e.preventDefault();try{await api("/api/v1/users/me/password",{method:"POST",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})});setCurrentPassword("");setNewPassword("");setMessage("Password changed. Sign in again with the new password.");await signOutFromTools()}catch(x){setError(x instanceof Error?x.message:"Could not change password")}}
  async function signOutFromTools(){accessToken="";currentRole="user";window.dispatchEvent(new Event("campuscare:session-expired"))}
  async function revoke(id:number){try{await api(`/api/v1/auth/sessions/${id}`,{method:"DELETE"});setSessions(await api<typeof sessions>("/api/v1/auth/sessions"));setMessage("Session revoked.")}catch(x){setError(x instanceof Error?x.message:"Could not revoke session")}}
  const activeGroup=groups.find(g=>g.id===selected)
  return <section style={{maxWidth:1180,margin:"28px auto",padding:"0 20px",display:"grid",gap:18}}>
    {(error||message)&&<p role="status" style={{color:error?"#b42318":"#067647"}}>{error||message}</p>}
    <div className="panel" style={{padding:24}}>
      <p className="eyebrow">ACCOUNT SECURITY</p><h2>Profile & sessions</h2>
      <form onSubmit={saveProfile} className="form-grid"><label>Full name<input value={newName} onChange={e=>setNewName(e.target.value)} required minLength={2}/></label><label>Email<input type="email" value={newEmail} onChange={e=>setNewEmail(e.target.value)} required/></label><button className="button primary">Save profile</button></form>
      <form onSubmit={changePassword} className="form-grid" style={{marginTop:18}}><label>Current password<input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} required/></label><label>New password<input type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} required minLength={8}/></label><button className="button secondary">Change password</button></form>
      <h3 style={{marginTop:24}}>Active sessions</h3>{sessions.map(s=><div key={s.id} style={{display:"flex",justifyContent:"space-between",gap:12,padding:"8px 0",borderBottom:"1px solid #eee"}}><span>Session #{s.id} · {s.ip_address||"IP unavailable"} · Expires {new Date(s.expires_at).toLocaleString()}</span><button className="button danger-ghost" onClick={()=>void revoke(s.id)}>Revoke</button></div>)}
    </div>
    <div className="panel" style={{padding:24}}>
      <p className="eyebrow">COLLABORATION</p><h2>Groups & shared work</h2>
      <form onSubmit={createGroup} style={{display:"flex",gap:8,flexWrap:"wrap"}}><input value={groupName} onChange={e=>setGroupName(e.target.value)} placeholder="New group name" required minLength={2}/><button className="button primary">Create group</button></form>
      <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"16px 0"}}>{groups.map(g=><button key={g.id} className={selected===g.id?"button primary":"button secondary"} onClick={()=>setSelected(g.id)}>{g.name}</button>)}</div>
      {activeGroup&&<><h3>{activeGroup.name}</h3><h4>Members and permissions</h4>{members.map(m=><div key={m.user_id} style={{padding:"6px 0"}}>User #{m.user_id} {m.is_owner?"(owner)":""} · Create: {m.can_create?"yes":"no"} · Edit: {m.can_edit?"yes":"no"} · Assign: {m.can_assign?"yes":"no"}</div>)}
      {activeGroup.owner_id===profile?.id&&<form onSubmit={addMember} style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginTop:12}}><input type="number" min="1" value={memberId} onChange={e=>setMemberId(e.target.value)} placeholder="User ID" required/><label><input type="checkbox" checked={permissions.can_create} onChange={e=>setPermissions({...permissions,can_create:e.target.checked})}/> Create</label><label><input type="checkbox" checked={permissions.can_edit} onChange={e=>setPermissions({...permissions,can_edit:e.target.checked})}/> Edit</label><label><input type="checkbox" checked={permissions.can_assign} onChange={e=>setPermissions({...permissions,can_assign:e.target.checked})}/> Assign</label><button className="button secondary">Save member permissions</button></form>}
      <h4 style={{marginTop:20}}>Shared records</h4>{records.map(r=><article key={r.id} style={{padding:12,border:"1px solid #eee",borderRadius:10,marginBottom:8}}><strong>{r.title}</strong><p>{r.body}</p><small>Assignee: {r.assignee_id??"Unassigned"}</small></article>)}
      <form onSubmit={addRecord} style={{display:"grid",gap:8,marginTop:12}}><input value={recordTitle} onChange={e=>setRecordTitle(e.target.value)} placeholder="Shared task title" required minLength={3}/><textarea value={recordBody} onChange={e=>setRecordBody(e.target.value)} placeholder="Description" required/><button className="button primary">Create shared record</button></form>
      {activeGroup.owner_id===profile?.id&&<div style={{display:"flex",gap:8,marginTop:12}}><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this group and all its shared records?")){await api(`/api/v1/groups/${selected}`,{method:"DELETE"});setSelected(null);await loadGroups()}}}>Delete group</button></div>}
      </>}
    </div>
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
  </div>{adminView&&user.role==="admin"?<AdminDashboard/>:<><ComplaintWorkspace/><WorkspaceTools/></>}</>
}
