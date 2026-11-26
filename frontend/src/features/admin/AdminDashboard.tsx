import { useEffect, useState } from "react"
import { api } from "../../services/api"
import { categories, statuses } from "../../types/domain"
import type { Category, Status } from "../../types/domain"

export default function AdminDashboard() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [users, setUsers] = useState<Array<{id:number;email:string;full_name:string;role:string;is_banned:boolean;status:"active"|"suspended"|"banned";suspended_until:string|null}>>([])
  const [activity, setActivity] = useState<Array<{id:number;event:string;user_id:number|null;created_at:string;detail:string|null;ip_address:string|null;user_agent:string|null}>>([])
  const [records,setRecords]=useState<Array<{id:number;title:string;category:string;status:string;owner_id:number|null}>>([])
  const [groups,setGroups]=useState<Array<{id:number;name:string;owner_id:number}>>([])
  const [security,setSecurity]=useState<{failed_logins_last_7_days:number;by_ip:Record<string,number>;by_account:Record<string,number>}|null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState("Policy violation")
  const [query, setQuery] = useState("")
  const [roleFilter,setRoleFilter]=useState("")
  const [statusFilter,setStatusFilter]=useState("")
  const [selectedUserIds,setSelectedUserIds]=useState<number[]>([])
  const [adminId,setAdminId]=useState<number|null>(null)
  const [userOffset,setUserOffset]=useState(0)
  const [userDetail,setUserDetail]=useState<any>(null)
  const [selectedRecordIds,setSelectedRecordIds]=useState<number[]>([])
  const [selectedGroupIds,setSelectedGroupIds]=useState<number[]>([])
  const [recordStatusFilter,setRecordStatusFilter]=useState("")
  const [recordCategoryFilter,setRecordCategoryFilter]=useState("")
  const [activityUser,setActivityUser]=useState("")
  const [groupQuery,setGroupQuery]=useState("")
  const [activityQuery,setActivityQuery]=useState("")
  const [activityEvent,setActivityEvent]=useState("")
  async function load() {
    setBusy(true); setError("")
    try {
      const [s, u, a, r, g, sec, me] = await Promise.all([
        api<Record<string,number>>("/api/v1/admin/stats"),
        api<typeof users>(`/api/v1/admin/users?q=${encodeURIComponent(query)}&role=${roleFilter}&status=${statusFilter}&offset=${userOffset}&limit=50`),
        api<typeof activity>(`/api/v1/admin/activity?limit=30&q=${encodeURIComponent(activityQuery)}&event=${activityEvent}${/^\d+$/.test(activityUser)?`&user_id=${activityUser}`:""}`),
        api<typeof records>(`/api/v1/admin/records?limit=100&status=${recordStatusFilter}&category=${recordCategoryFilter}`),
        api<typeof groups>(`/api/v1/admin/groups?q=${encodeURIComponent(groupQuery)}`),
        api<typeof security>("/api/v1/admin/security"),
        api<{id:number}>("/api/v1/users/me"),
      ])
      setStats(s); setUsers(u); setActivity(a); setRecords(r); setGroups(g); setSecurity(sec); setAdminId(me.id)
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load admin data") }
    finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [userOffset])
  async function act(userId:number, action:"ban"|"unban"|"promote"|"demote") {
    try {
      if(action==="ban") await api(`/api/v1/admin/users/${userId}/ban`, {method:"POST",body:JSON.stringify({reason})})
      if(action==="unban") await api(`/api/v1/admin/users/${userId}/unban`, {method:"POST",body:JSON.stringify({reason})})
      if(action==="promote") await api(`/api/v1/admin/users/${userId}/role`, {method:"PATCH",body:JSON.stringify({role:"admin"})})
      if(action==="demote") await api(`/api/v1/admin/users/${userId}/role`, {method:"PATCH",body:JSON.stringify({role:"user"})})
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
    <div style={{display:"flex",gap:8,marginBottom:12,flexWrap:"wrap"}}><input aria-label="Search users" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search name or email"/><select value={roleFilter} onChange={e=>setRoleFilter(e.target.value)}><option value="">All roles</option><option value="user">User</option><option value="admin">Admin</option></select><select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="banned">Banned</option></select><button className="button secondary" onClick={()=>void load()}>Search / filter</button></div><div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:12}}><button className="button danger-ghost" disabled={!selectedUserIds.length} onClick={async()=>{try{await api(`/api/v1/admin/users/bulk-ban?reason=${encodeURIComponent(reason)}`,{method:"POST",body:JSON.stringify(selectedUserIds)});setSelectedUserIds([]);await load()}catch(e){setError(e instanceof Error?e.message:"Bulk ban failed")}}}>Bulk ban selected</button><button className="button secondary" disabled={!selectedUserIds.length} onClick={async()=>{try{await api(`/api/v1/admin/users/bulk-unban?reason=${encodeURIComponent(reason)}`,{method:"POST",body:JSON.stringify(selectedUserIds)});setSelectedUserIds([]);await load()}catch(e){setError(e instanceof Error?e.message:"Bulk unban failed")}}}>Bulk unban selected</button></div>
    <label>Reason for ban / unban <input value={reason} onChange={e=>setReason(e.target.value)} /></label>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Select</th><th>ID</th><th>User</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {users.map(u=><tr key={u.id}><td><input type="checkbox" checked={selectedUserIds.includes(u.id)} onChange={e=>setSelectedUserIds(e.target.checked?[...selectedUserIds,u.id]:selectedUserIds.filter(id=>id!==u.id))}/></td><td>{u.id}</td><td>{u.full_name}<br/><small>{u.email}</small></td><td>{u.role}</td><td><span className={`account-status ${u.status}`}>{u.status}</span></td><td style={{display:"flex",gap:6,flexWrap:"wrap"}}><button className="button secondary" onClick={async()=>{try{setUserDetail(await api(`/api/v1/admin/users/${u.id}`))}catch(e){setError(e instanceof Error?e.message:"Could not load user")}}}>Details</button><button className="button secondary" onClick={async()=>{try{await api(`/api/v1/admin/users/${u.id}/revoke-sessions`,{method:"POST"});await load()}catch(e){setError(e instanceof Error?e.message:"Could not revoke sessions")}}}>Revoke sessions</button>{u.role==="user" && <button className="button secondary" onClick={()=>void act(u.id,"promote")}>Make admin</button>}{u.role==="admin" && u.id!==adminId && <button className="button secondary" onClick={()=>void act(u.id,"demote")}>Make user</button>}{u.role==="user" && (u.is_banned?<button className="button secondary" onClick={()=>void act(u.id,"unban")}>Unban</button>:<button className="button danger-ghost" onClick={()=>void act(u.id,"ban")}>Ban</button>)}</td></tr>)}
    </tbody></table></div><div style={{display:"flex",gap:8,marginTop:10}}><button className="button secondary" disabled={userOffset===0} onClick={()=>setUserOffset(Math.max(0,userOffset-50))}>Previous users</button><button className="button secondary" disabled={users.length<50} onClick={()=>setUserOffset(userOffset+50)}>Next users</button><span>Offset {userOffset}</span></div>
    {userDetail&&<div className="panel" style={{padding:16,marginTop:16}}><button className="button secondary" onClick={()=>setUserDetail(null)}>Close details</button><h3>{userDetail.user.full_name} · {userDetail.user.email}</h3><p>Role: {userDetail.user.role} · Status: {userDetail.user.is_banned?`banned (${userDetail.user.ban_reason??"no reason"})`:"active"} · Joined {new Date(userDetail.user.created_at).toLocaleDateString()}</p><p>Complaints: {userDetail.complaints.length} · Groups: {userDetail.groups.length} · Sessions: {userDetail.sessions.length} · Recent events: {userDetail.activity.length}</p><h4>Sessions</h4><ul>{userDetail.sessions.length===0?<li>No sessions.</li>:userDetail.sessions.slice(0,8).map((x:any)=><li key={x.id}>#{x.id} · {x.ip_address??"IP unknown"} · {x.revoked_at?"revoked":"active"} · {new Date(x.created_at).toLocaleString()}</li>)}</ul><h4>Recent complaints</h4><ul>{userDetail.complaints.slice(0,5).map((c:any)=><li key={c.id}>#{c.id} {c.title} — {c.status}</li>)}</ul><h4>Groups</h4><ul>{userDetail.groups.map((g:any)=><li key={g.id}>{g.name} (#{g.id})</li>)}</ul><h4>Recent activity</h4><ul>{userDetail.activity.slice(0,5).map((a:any)=><li key={a.id}>{a.event} · {new Date(a.created_at).toLocaleString()}</li>)}</ul></div>}
    <h3 style={{marginTop:28}}>Content moderation</h3>
    <h4>Complaints</h4>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}><select value={recordStatusFilter} onChange={e=>setRecordStatusFilter(e.target.value)}><option value="">All statuses</option><option value="pending">Pending</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option><option value="rejected">Rejected</option></select><select value={recordCategoryFilter} onChange={e=>setRecordCategoryFilter(e.target.value)}><option value="">All categories</option>{categories.map(c=><option key={c.value} value={c.value}>{c.label}</option>)}</select><button className="button secondary" onClick={()=>void load()}>Filter records</button><button className="button danger-ghost" disabled={!selectedRecordIds.length} onClick={async()=>{if(confirm("Delete selected complaints?")){await api("/api/v1/admin/records/bulk-delete",{method:"POST",body:JSON.stringify(selectedRecordIds)});setSelectedRecordIds([]);await load()}}}>Delete selected ({selectedRecordIds.length})</button></div>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Select</th><th>ID</th><th>Title</th><th>Category</th><th>Status</th><th>Action</th></tr></thead><tbody>{records.map(r=><tr key={r.id}><td><input type="checkbox" checked={selectedRecordIds.includes(r.id)} onChange={e=>setSelectedRecordIds(e.target.checked?[...selectedRecordIds,r.id]:selectedRecordIds.filter(id=>id!==r.id))}/></td><td>{r.id}</td><td>{r.title}</td><td>{r.category}</td><td>{r.status}</td><td><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this complaint permanently?")){try{await api(`/api/v1/admin/records/${r.id}`,{method:"DELETE"});await load()}catch(e){setError(e instanceof Error?e.message:"Delete failed")}}}}>Delete</button></td></tr>)}</tbody></table></div>
    <h4 style={{marginTop:20}}>Shared groups</h4>
    {groups.map(g=><div key={g.id} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid #eee"}}><span>{g.name} · owner #{g.owner_id}</span><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this group and its shared records?")){try{await api(`/api/v1/admin/groups/${g.id}`,{method:"DELETE"});await load()}catch(e){setError(e instanceof Error?e.message:"Delete failed")}}}}>Delete group</button></div>)}
    <h3 style={{marginTop:28}}>Security monitoring</h3>
    {security&&<><p>Failed logins in last 7 days: <strong>{security.failed_logins_last_7_days}</strong></p><p>By IP: {Object.entries(security.by_ip).map(([ip,n])=>`${ip} (${n})`).join(", ")||"No failed logins"}</p><p>By account: {Object.entries(security.by_account).map(([email,n])=>`${email} (${n})`).join(", ")||"No failed logins"}</p></>}
    <h3 style={{marginTop:28}}>Recent activity</h3>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}><input value={activityQuery} onChange={e=>setActivityQuery(e.target.value)} placeholder="Search event, IP or detail"/><input value={activityUser} onChange={e=>setActivityUser(e.target.value)} placeholder="User ID" inputMode="numeric" style={{width:90}}/><select value={activityEvent} onChange={e=>setActivityEvent(e.target.value)}><option value="">All events</option><option value="login">Login</option><option value="failed_login">Failed login</option><option value="logout">Logout</option><option value="password_change">Password change</option><option value="role_change">Role change</option><option value="user_banned">Ban</option><option value="user_unbanned">Unban</option><option value="data_export">Export</option></select><button className="button secondary" onClick={()=>void load()}>Filter activity</button></div>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Event</th><th>User ID</th><th>Details</th><th>IP address</th><th>Browser</th><th>Time</th></tr></thead><tbody>{activity.length===0?<tr><td colSpan={6}>No activity matches these filters.</td></tr>:activity.map(a=><tr key={a.id}><td>{a.event}</td><td>{a.user_id??"—"}</td><td>{a.detail??"—"}</td><td>{a.ip_address??"—"}</td><td title={a.user_agent??""}>{(a.user_agent??"—").slice(0,40)}</td><td>{new Date(a.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>
    <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:18}}>{["users","records","activity"].map(k=><a key={k} className="button secondary" href={`/api/v1/admin/export/${k}`} onClick={async e=>{e.preventDefault();try{const params=k==="users"?`?q=${encodeURIComponent(query)}&role=${roleFilter}&status=${statusFilter}`:k==="records"?`?status=${recordStatusFilter}&category=${recordCategoryFilter}`:`?q=${encodeURIComponent(activityQuery)}&event=${activityEvent}${/^\\d+$/.test(activityUser)?`&user_id=${activityUser}`:""}`;const data=await api<string>(`/api/v1/admin/export/${k}${params}`);const blob=new Blob([data],{type:"text/csv"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`campuscare-${k}.csv`;link.click();URL.revokeObjectURL(url)}catch(err){setError(err instanceof Error?err.message:"Export failed")}}}>Export {k} CSV</a>)}</div>
  </section>
}
