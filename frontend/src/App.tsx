import { useCallback, useEffect, useState } from "react"
import type { FormEvent } from "react"
import { api, setAccessToken, setCurrentRole } from "./services/api"
import type { Page } from "./types/domain"
import { PAGES } from "./types/domain"
import { pageFromHash } from "./utils/navigation"
import ComplaintWorkspace from "./features/complaints/ComplaintWorkspace"
import AdminDashboard from "./features/admin/AdminDashboard"
import UserManagementPage from "./features/admin/UserManagementPage"
import WorkspaceTools from "./features/profile/WorkspaceTools"

export default function App() {
  const [restoring, setRestoring] = useState(true)
  const [user, setUser] = useState<{id:number;email:string;full_name:string;role:"user"|"admin"}|null>(null)
  const [mode, setMode] = useState<"login"|"signup">("login")
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [page, setPageState] = useState<Page>(pageFromHash)
  const setPage = useCallback((next: Page) => {
    window.location.hash = next === "home" ? "" : `/${next}`
    setPageState(next)
  }, [])

  useEffect(() => {
    let alive = true
    fetch("/api/v1/auth/refresh",{method:"POST",credentials:"include"}).then(async r=>{
      if(!r.ok) return null
      return r.json()
    }).then(async tokens=>{
      if(!tokens || !alive) return
      setAccessToken(tokens.access_token)
      const me=await api<{id:number;email:string;full_name:string;role:"user"|"admin"}>("/api/v1/users/me")
      if(alive){setCurrentRole(me.role);setUser(me)}
    }).catch(()=>{}).finally(()=>{if(alive)setRestoring(false)})
    const expired=()=>{if(alive){setAccessToken("");setCurrentRole("user");setUser(null);setPage("home");setError("Your session expired. Please sign in again.")}}
    const onHash=()=>{if(alive)setPageState(pageFromHash())}
    window.addEventListener("campuscare:session-expired",expired)
    window.addEventListener("hashchange",onHash)
    return ()=>{alive=false;window.removeEventListener("campuscare:session-expired",expired);window.removeEventListener("hashchange",onHash)}
  },[])

  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();setBusy(true);setError("")
    try {
      if(mode==="signup") await api("/api/v1/auth/signup",{method:"POST",body:JSON.stringify({email,full_name:name,password})})
      const tokens=await api<{access_token:string;user:{id:number;email:string;full_name:string;role:"user"|"admin"}}>("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})})
      setAccessToken(tokens.access_token);setCurrentRole(tokens.user.role);setUser(tokens.user)
    } catch(err) {setError(err instanceof Error?err.message:"Authentication failed")}
    finally {setBusy(false)}
  }

  async function signOut() {
    try {await api("/api/v1/auth/logout",{method:"POST"})} catch {}
    setAccessToken("");setCurrentRole("user");setUser(null);setPage("home")
  }

  if(restoring) return <main className="app-shell"><div className="panel" style={{margin:"12vh auto",maxWidth:480,padding:32}}>Restoring secure session…</div></main>

  if(!user) return <main className="app-shell"><section className="panel auth-panel">
    <a className="brand auth-brand" href="/" aria-label="CampusCare home"><span className="brand-mark">CC</span><span><strong>CampusCare</strong><small>Complaint management</small></span></a>
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

  const navItems: {id:Page;label:string}[] = [
    {id:"home",label:"Home"},{id:"about",label:"About"},{id:"complaints",label:"Complaints"},
    {id:"profile",label:"My Profile"},{id:"contact",label:"Contact"},
    ...(user.role==="admin"?[{id:"admin" as const,label:"Admin"},{id:"users" as const,label:"Users"}]:[]),
  ]

  return <div className="site-frame">
    <header className="site-header">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setPage("home")}} aria-label="CampusCare home">
        <span className="brand-mark">CC</span><span><strong>CampusCare</strong><small>Complaint management</small></span>
      </a>
      <nav className="main-nav" aria-label="Main navigation">
        {navItems.map(item=><button key={item.id} className={page===item.id?"nav-link active":"nav-link"} aria-current={page===item.id?"page":undefined} onClick={()=>setPage(item.id)}>{item.label}</button>)}
      </nav>
      <div className="account-menu"><span className="account-identity"><strong>{user.full_name}</strong><small>{user.role==="admin"?"Administrator":"Student account"}</small></span><button className="button secondary signout-button" onClick={()=>void signOut()}>Sign out</button></div>
    </header>

    <main className="page-content">
      {page==="home"&&<section className="home-page">
        <div className="home-hero">
          <div><p className="eyebrow">INDEPENDENT UNIVERSITY, BANGLADESH</p><h1>A better campus<br/><em>starts with being heard.</em></h1>
            <p className="hero-copy">CampusCare makes it easier to report campus issues, follow their progress, and work together for a better university experience.</p>
            <div className="home-actions"><button className="button primary" onClick={()=>setPage("complaints")}>Go to complaints <span aria-hidden="true">→</span></button><button className="button secondary" onClick={()=>setPage("about")}>Learn about CampusCare</button></div>
          </div><div className="home-illustration" aria-hidden="true"><span>CC</span><i>✳</i></div>
        </div>
        <div className="home-section-heading"><div><p className="eyebrow">YOUR CAMPUS, YOUR VOICE</p><h2>What would you like to do?</h2></div></div>
        <div className="feature-grid">
          <button className="feature-card" onClick={()=>setPage("complaints")}><span className="feature-icon">＋</span><strong>Submit a complaint</strong><p>Report an issue and provide the details needed to resolve it.</p><span className="feature-link">Open complaints →</span></button>
          <button className="feature-card" onClick={()=>setPage("complaints")}><span className="feature-icon">☷</span><strong>Track progress</strong><p>See complaint status updates and administration responses.</p><span className="feature-link">Track a complaint →</span></button>
          <button className="feature-card" onClick={()=>setPage("profile")}><span className="feature-icon">◎</span><strong>Manage your account</strong><p>Update your profile, password, sessions, and group workspace.</p><span className="feature-link">Open my profile →</span></button>
          {user.role==="admin"&&<button className="feature-card admin-feature" onClick={()=>setPage("admin")}><span className="feature-icon">▦</span><strong>Admin dashboard</strong><p>Manage users, review complaints, and monitor campus activity.</p><span className="feature-link">Open administration →</span></button>}
        </div>
        <div className="home-note"><span>✳</span><p><strong>Every report matters.</strong> Your feedback helps the university identify issues and improve campus life.</p></div>
      </section>}

      {page==="about"&&<section className="info-page panel">
        <p className="eyebrow">ABOUT THE PLATFORM</p><h1>Making campus feedback <em>easier.</em></h1>
        <p className="info-lead">CampusCare is a campus complaint management system designed to give students a clear, organized way to report problems and follow their resolution.</p>
        <div className="info-grid"><article><span>01</span><h3>Report</h3><p>Submit a complaint with a title, category, and description so the issue is easy to understand.</p></article><article><span>02</span><h3>Track</h3><p>Follow the status of your complaint from Pending to In progress and Resolved.</p></article><article><span>03</span><h3>Improve</h3><p>Administration can review reports, respond, and take action to improve campus services.</p></article></div>
        <button className="button primary" onClick={()=>setPage("complaints")}>Visit complaints <span aria-hidden="true">→</span></button>
      </section>}

      {page==="complaints"&&<ComplaintWorkspace/>}
      {page==="profile"&&<WorkspaceTools/>}
      {page==="admin"&&user.role==="admin"&&<AdminDashboard/>}
      {page==="users"&&user.role==="admin"&&<UserManagementPage/>}
      {(page==="admin"||page==="users")&&user.role!=="admin"&&<section className="info-page panel" role="alert"><p className="eyebrow">ACCESS DENIED</p><h1>Administrators <em>only.</em></h1><p className="info-lead">Your account does not have permission to open this page. The server enforces the same rule on every admin request.</p><button className="button primary" onClick={()=>setPage("home")}>Back to home</button></section>}

      {page==="contact"&&<section className="info-page contact-page panel">
        <p className="eyebrow">WE ARE HERE TO HELP</p><h1>Contact & <em>support.</em></h1>
        <p className="info-lead">For an issue with your account or the complaint process, use the options below to find the right place for help.</p>
        <div className="contact-options"><article><span className="feature-icon">☷</span><h3>Complaint support</h3><p>Submit a complaint with enough detail for the administration to review it.</p><button className="refresh-link" onClick={()=>setPage("complaints")}>Open complaints →</button></article><article><span className="feature-icon">⌘</span><h3>Technical documentation</h3><p>View the API documentation for the CampusCare application.</p><a className="feature-link" href="/api/docs" target="_blank" rel="noreferrer">Open API docs ↗</a></article></div>
      </section>}
    </main>
    <footer className="site-footer"><span>CampusCare · Secure campus feedback</span><span>Independent University, Bangladesh</span><a href="/api/docs" target="_blank" rel="noreferrer">API documentation ↗</a></footer>
  </div>
}
