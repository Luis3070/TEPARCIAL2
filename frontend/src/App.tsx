import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { lazy, Suspense, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, BarChart3, Box, CalendarDays, Camera, ChevronDown, CircleGauge, ClipboardList, Home, Menu, ShieldCheck, Wrench, Settings2, WifiOff, Database } from 'lucide-react'
import { api } from './services/api'
import { useUI } from './state'
const OverviewPage=lazy(()=>import('./pages/OverviewPage').then(m=>({default:m.OverviewPage})))
const StructuralPage=lazy(()=>import('./pages/StructuralPage').then(m=>({default:m.StructuralPage})))
const InspectionsPage=lazy(()=>import('./pages/InspectionsPage').then(m=>({default:m.InspectionsPage})))
const AnalyticsPage=lazy(()=>import('./pages/AnalyticsPage').then(m=>({default:m.AnalyticsPage})))
const MaintenancePage=lazy(()=>import('./pages/MaintenancePage').then(m=>({default:m.MaintenancePage})))
const PlanningPage=lazy(()=>import('./pages/PlanningPage').then(m=>({default:m.PlanningPage})))
const EvidencePage=lazy(()=>import('./pages/EvidencePage').then(m=>({default:m.EvidencePage})))
const SettingsPage=lazy(()=>import('./pages/SettingsPage').then(m=>({default:m.SettingsPage})))
const AssetSelectionPage=lazy(()=>import('./pages/AssetSelectionPage').then(m=>({default:m.AssetSelectionPage})))

const groups=[
 {label:'ASSET MONITORING',items:[{to:'/',name:'Overview',icon:Home},{to:'/structural-3d',name:'Structural 3D',icon:Box},{to:'/inspections',name:'Inspections',icon:ClipboardList},{to:'/analytics',name:'Crack analytics',icon:BarChart3}]},
 {label:'MAINTENANCE',items:[{to:'/maintenance',name:'Recommendations',icon:Wrench},{to:'/planning',name:'Planning & work orders',icon:CalendarDays},{to:'/evidence',name:'Evidence',icon:Camera}]},
 {label:'SYSTEM',items:[{to:'/settings',name:'Settings & calibration',icon:Settings2}]},
]
const titleByPath:Record<string,string>={'/':'Overview','/asset-selection':'Active asset','/structural-3d':'Structural Digital Twin','/inspections':'Inspections','/analytics':'Crack analytics','/maintenance':'Maintenance recommendations','/planning':'Maintenance planning','/evidence':'Evidence library','/settings':'Settings & calibration'}

export default function App(){
 const location=useLocation();const navigate=useNavigate();const selectedId=useUI(s=>s.selectedInspectionId);const setInspection=useUI(s=>s.setInspection);const notice=useUI(s=>s.notice);const clearNotice=useUI(s=>s.clearNotice)
 const health=useQuery({queryKey:['health'],queryFn:api.health,refetchInterval:30_000})
 const inspections=useQuery({queryKey:['inspections','shell'],queryFn:()=>api.inspections({limit:100})})
 const ordered=[...(inspections.data||[])].sort((a,b)=>b.date.localeCompare(a.date))
 const active=ordered.find(i=>i.id===selectedId)||ordered[0]
 useEffect(()=>{if(selectedId===undefined&&ordered[0])setInspection(ordered[0].id)},[selectedId,ordered[0]?.id,setInspection])
 const currentTitle=titleByPath[location.pathname]||'Integrity management'
 return <div className="app-shell">
  <aside className="sidebar">
   <div className="brand"><div className="brand-mark"><span/><span/><span/></div><div><strong>EH4000</strong><small>STRUCTURAL INTEGRITY</small></div></div>
   <div className="asset-switcher"><span className="tiny-label">ACTIVE ASSET</span><button aria-label="Abrir selector de equipo EH4-01" onClick={()=>navigate('/asset-selection')}><span className="asset-avatar">EH</span><span><b>EH4-01</b><small>EH4000 Mining Truck</small></span><ChevronDown size={15}/></button><div className="asset-online"><i/> Local historical dataset</div></div>
   <nav className="side-nav">{groups.map(g=><div className="nav-group" key={g.label}><span className="nav-group-label">{g.label}</span>{g.items.map(item=><NavLink key={item.to} to={item.to} end={item.to==='/'} className={({isActive})=>`nav-item ${isActive?'active':''}`}><item.icon size={17}/><span>{item.name}</span>{item.to==='/maintenance'&&<b className="nav-count">4</b>}</NavLink>)}</div>)}</nav>
   <div className="sidebar-bottom"><div className="asset-health"><div className="health-icon"><ShieldCheck size={17}/></div><div><small>DATA CONNECTION</small><b>{health.isSuccess?'Connected':'Connecting…'}</b></div><span className={`health-led ${health.isSuccess?'ok':'wait'}`}/></div><div className="sidebar-foot"><Database size={13}/> QA verified · EH4-01</div></div>
  </aside>
  <main className="main-shell">
   <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><span/><span/><span/></div>EH4000</div><div className="breadcrumb"><span>Structural Integrity</span><b>/</b><strong>{currentTitle}</strong></div><div className="topbar-right">
     <div className="historical-label"><WifiOff size={14}/><span>Historical dataset</span><i/></div>
     <label className="inspection-select"><span>INSPECTION</span><select value={active?.id??''} onChange={e=>setInspection(e.target.value?Number(e.target.value):undefined)}>{ordered.map(i=><option key={i.id} value={i.id}>{i.date} · {i.hours.toLocaleString('es-CO')} h</option>)}</select><ChevronDown size={13}/></label>
     <div className="profile-avatar">{active?.inspector.slice(-2)||'EH'}</div>
   </div></header>
   {!health.isSuccess&&<div className="api-banner"><WifiOff size={15}/><span>{health.isError?'No se puede conectar con FastAPI. Inicia el backend en http://127.0.0.1:8000.':'Conectando con el servicio local…'}</span></div>}
   <div className="page-container"><Suspense fallback={<div className="page-loading"><span className="loader-ring"/> Loading module…</div>}><Routes>
    <Route path="/" element={<OverviewPage/>}/><Route path="/asset-selection" element={<AssetSelectionPage/>}/><Route path="/structural-3d" element={<StructuralPage/>}/><Route path="/inspections" element={<InspectionsPage/>}/><Route path="/analytics" element={<AnalyticsPage/>}/><Route path="/maintenance" element={<MaintenancePage/>}/><Route path="/planning" element={<PlanningPage/>}/><Route path="/evidence" element={<EvidencePage/>}/><Route path="/settings" element={<SettingsPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/>
   </Routes></Suspense></div>
   {notice&&<div className={`toast toast-${notice.kind}`} role="status"><span>{notice.text}</span><button onClick={clearNotice}>×</button></div>}
  </main>
 </div>
}
