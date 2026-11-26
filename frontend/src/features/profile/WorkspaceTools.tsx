import { useEffect, useState } from "react"
import type { FormEvent } from "react"
import { api, setAccessToken, setCurrentRole } from "../../services/api"

export default function WorkspaceTools() {
  const [groups,setGroups]=useState<Array<{id:number;name:string;owner_id:number}>>([])
  const [selected,setSelected]=useState<number|null>(null)
  const [members,setMembers]=useState<Array<{user_id:number;full_name:string|null;email:string|null;can_create:boolean;can_edit:boolean;can_assign:boolean;is_owner:boolean}>>([])
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
  async function signOutFromTools(){setAccessToken("");setCurrentRole("user");window.dispatchEvent(new Event("campuscare:session-expired"))}
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
      {activeGroup&&<><h3>{activeGroup.name}</h3><h4>Members and permissions</h4>{members.map(m=><div key={m.user_id} style={{padding:"6px 0",display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}><span>{m.full_name??"User"} (#{m.user_id}) {m.is_owner?"(owner)":""} · Create: {m.can_create?"yes":"no"} · Edit: {m.can_edit?"yes":"no"} · Assign: {m.can_assign?"yes":"no"}</span>{activeGroup.owner_id===profile?.id&&!m.is_owner&&<button className="button danger-ghost" onClick={async()=>{await api(`/api/v1/groups/${selected}/members/${m.user_id}`,{method:"DELETE"});await loadSelected(selected!)}}>Remove member</button>}</div>)}
      {activeGroup.owner_id===profile?.id&&<form onSubmit={addMember} style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginTop:12}}><input type="number" min="1" value={memberId} onChange={e=>setMemberId(e.target.value)} placeholder="User ID" required/><label><input type="checkbox" checked={permissions.can_create} onChange={e=>setPermissions({...permissions,can_create:e.target.checked})}/> Create</label><label><input type="checkbox" checked={permissions.can_edit} onChange={e=>setPermissions({...permissions,can_edit:e.target.checked})}/> Edit</label><label><input type="checkbox" checked={permissions.can_assign} onChange={e=>setPermissions({...permissions,can_assign:e.target.checked})}/> Assign</label><button className="button secondary">Save member permissions</button></form>}
      <h4 style={{marginTop:20}}>Shared records</h4>{records.map(r=><article key={r.id} style={{padding:12,border:"1px solid #eee",borderRadius:10,marginBottom:8}}><strong>{r.title}</strong><p>{r.body}</p><small>Assignee: {r.assignee_id??"Unassigned"}</small><div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:8}}>{(activeGroup.owner_id===profile?.id||members.find(m=>m.user_id===profile?.id)?.can_edit)&&<button className="button secondary" onClick={async()=>{const body=prompt("Update shared record description",r.body);if(body!==null){await api(`/api/v1/groups/${selected}/records/${r.id}`,{method:"PATCH",body:JSON.stringify({body})});await loadSelected(selected!)}}}>Edit record</button>}{(activeGroup.owner_id===profile?.id||members.find(m=>m.user_id===profile?.id)?.can_assign)&&<button className="button secondary" onClick={async()=>{const value=prompt("Assign to user ID (leave blank to unassign)",r.assignee_id?String(r.assignee_id):"");if(value!==null){await api(`/api/v1/groups/${selected}/records/${r.id}`,{method:"PATCH",body:JSON.stringify({assignee_id:value.trim()?Number(value):null})});await loadSelected(selected!)}}}>Assign</button>}</div></article>)}
      {(activeGroup.owner_id===profile?.id||members.find(m=>m.user_id===profile?.id)?.can_create)&&<form onSubmit={addRecord} style={{display:"grid",gap:8,marginTop:12}}><input value={recordTitle} onChange={e=>setRecordTitle(e.target.value)} placeholder="Shared task title" required minLength={3}/><textarea value={recordBody} onChange={e=>setRecordBody(e.target.value)} placeholder="Description" required/><button className="button primary">Create shared record</button></form>}
      {activeGroup.owner_id===profile?.id&&<div style={{display:"flex",gap:8,marginTop:12}}><button className="button secondary" onClick={async()=>{const name=prompt("New group name",activeGroup.name);if(name){await api(`/api/v1/groups/${selected}`,{method:"PATCH",body:JSON.stringify({name})});await loadGroups();await loadSelected(selected!)}}}>Rename group</button><button className="button danger-ghost" onClick={async()=>{if(confirm("Delete this group and all its shared records?")){await api(`/api/v1/groups/${selected}`,{method:"DELETE"});setSelected(null);await loadGroups()}}}>Delete group</button></div>}
      </>}
    </div>
  </section>
}
