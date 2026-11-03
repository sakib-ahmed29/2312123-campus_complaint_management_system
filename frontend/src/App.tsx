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

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  })
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

export default function App() {
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
            {activeComplaint.status === "pending" || activeComplaint.status === "in_progress" ? <div className="admin-tools">
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
