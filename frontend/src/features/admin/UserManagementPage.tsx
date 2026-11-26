import { useCallback, useEffect, useState } from "react"
import { api } from "../../services/api"
import type { ManagedUser } from "../../types/domain"

export default function UserManagementPage() {
  const [users,setUsers]=useState<ManagedUser[]>([])
  const [query,setQuery]=useState("")
  const [role,setRole]=useState("")
  const [status,setStatus]=useState("")
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState("")
  const [notice,setNotice]=useState("")
  const [busyId,setBusyId]=useState<number|null>(null)
  const load=useCallback(async()=>{
    setLoading(true);setError("")
    try{
      const params=new URLSearchParams({q:query,limit:"100"})
      if(role)params.set("role",role)
      if(status)params.set("status",status)
      setUsers(await api<ManagedUser[]>(`/api/v1/admin/users?${params.toString()}`))
    }catch(e){setError(e instanceof Error?e.message:"Could not load users")}
    finally{setLoading(false)}
  },[query,role,status])
  useEffect(()=>{void load()},[load])
  async function manage(user:ManagedUser,action:"ban"|"unban"|"suspend"|"unsuspend"){
    const reason=window.prompt("Enter the reason for this account action:",action==="ban"?"Policy violation":"Administrative review")
    if(reason===null)return
    if(reason.trim().length<3){setError("Please enter a reason with at least 3 characters.");return}
    let payload:Record<string,unknown>={reason:reason.trim()}
    if(action==="suspend"){
      const raw=window.prompt("Suspension duration in hours (1–720):","24")
      if(raw===null)return
      const hours=Number(raw)
      if(!Number.isInteger(hours)||hours<1||hours>720){setError("Enter a whole number from 1 to 720 hours.");return}
      payload={...payload,hours}
    }
    setBusyId(user.id);setError("");setNotice("")
    try{
      await api(`/api/v1/admin/users/${user.id}/${action}`,{method:"POST",body:JSON.stringify(payload)})
      setNotice(`${user.full_name}'s account was updated successfully.`)
      await load()
    }catch(e){setError(e instanceof Error?e.message:"Could not update account")}
    finally{setBusyId(null)}
  }
  const totals={active:users.filter(u=>u.status==="active").length,suspended:users.filter(u=>u.status==="suspended").length,banned:users.filter(u=>u.status==="banned").length}
  return <section className="user-management-page">
    <div className="user-page-heading"><div><p className="eyebrow">CAMPUSCARE ADMINISTRATION</p><h1>User management</h1><p className="muted">Review accounts and control access to CampusCare.</p></div><button className="button secondary" onClick={()=>void load()} disabled={loading}>{loading?"Refreshing…":"↻ Refresh"}</button></div>
    <div className="user-status-summary"><article><span>Active</span><strong>{totals.active}</strong></article><article><span>Suspended</span><strong>{totals.suspended}</strong></article><article><span>Banned</span><strong>{totals.banned}</strong></article><article><span>Showing</span><strong>{users.length}</strong></article></div>
    {(error||notice)&&<div className={error?"alert error-alert":"alert success-alert"} role="status">{error||notice}<button onClick={()=>{setError("");setNotice("")}} aria-label="Dismiss">×</button></div>}
    <div className="panel user-directory"><div className="user-directory-heading"><div><p className="eyebrow">ACCOUNT DIRECTORY</p><h2>All registered users</h2></div></div>
      <div className="user-filters"><label>Search<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search name or email"/></label><label>Role<select value={role} onChange={e=>setRole(e.target.value)}><option value="">All roles</option><option value="user">User</option><option value="admin">Admin</option></select></label><label>Status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="banned">Banned</option></select></label><button className="button primary" onClick={()=>void load()}>Apply filters</button></div>
      <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Account</th><th>Role</th><th>Status</th><th>Restriction details</th><th>Actions</th></tr></thead><tbody>
        {loading?<tr><td colSpan={5} className="table-empty">Loading accounts…</td></tr>:users.length===0?<tr><td colSpan={5} className="table-empty">No matching accounts found.</td></tr>:users.map(u=><tr key={u.id}>
          <td><strong>{u.full_name}</strong><small>{u.email}</small><small>Account #{u.id}</small></td><td><span className={u.role==="admin"?"role-label admin-role":"role-label"}>{u.role}</span></td><td><span className={`account-status ${u.status}`}>{u.status}</span></td>
          <td>{u.status==="banned"?(u.ban_reason||"No reason recorded"):u.status==="suspended"?<><span>Until {new Date(u.suspended_until||"").toLocaleString()}</span><small>{u.suspension_reason||"No reason recorded"}</small></>:"No restriction"}</td>
          <td><div className="user-actions">{u.role==="admin"?<span className="muted">Admin account protected</span>:<>
            {u.status==="active"&&<button className="button secondary" disabled={busyId===u.id} onClick={()=>void manage(u,"suspend")}>Suspend</button>}
            {u.status==="suspended"&&<button className="button secondary" disabled={busyId===u.id} onClick={()=>void manage(u,"unsuspend")}>Unsuspend</button>}
            {u.status==="banned"?<button className="button secondary" disabled={busyId===u.id} onClick={()=>void manage(u,"unban")}>Unban</button>:<button className="button danger-ghost" disabled={busyId===u.id} onClick={()=>void manage(u,"ban")}>Ban</button>}
          </>}</div></td>
        </tr>)}
      </tbody></table></div>
      <p className="user-page-note">Suspensions last from 1 hour to 30 days. Suspended users cannot sign in and existing sessions are revoked. Admin accounts are protected from ban and suspension actions.</p>
    </div>
  </section>
}
