import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, Check, Clock3, Play, Plus, RotateCcw, X, ClipboardList } from 'lucide-react'
import { api } from '../services/api'
import { useUI } from '../state'
import { PageHeader } from '../components/PageHeader'
import { PriorityBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import type { WorkOrder } from '../types'

export function PlanningPage(){
 const qc=useQueryClient();const notify=useUI(s=>s.notify);const [filter,setFilter]=useState('ALL');const [expanded,setExpanded]=useState<number|null>(null);const navigate=useNavigate()
 const orders=useQuery({queryKey:['work-orders'],queryFn:()=>api.workOrders()})
 const history=useQuery({queryKey:['workorder-history',expanded],queryFn:()=>api.workOrderHistory(expanded!),enabled:!!expanded})
 const mutation=useMutation({mutationFn:({id,body}:{id:number;body:unknown})=>api.updateWorkOrder(id,body),onSuccess:async()=>{await qc.invalidateQueries();notify('success','Work order updated and audit history recorded.')},onError:e=>notify('error',e.message)})
 const allRows=(orders.data||[]).slice().sort((a,b)=>(a.scheduled_date||'9999-12-31').localeCompare(b.scheduled_date||'9999-12-31'))
 const rows=filter==='OPEN'?allRows.filter(o=>!['COMPLETED','CANCELED'].includes(o.status)):filter==='ALL'?allRows:allRows.filter(o=>o.status===filter)
 const counts=['PENDING','APPROVED','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELED'].map(status=>({status,count:(orders.data||[]).filter(o=>o.status===status).length}))
 return <>
  <PageHeader eyebrow="MAINTENANCE PLANNING" title="Work orders" description="Planificación con aprobación explícita. Las recomendaciones no se convierten automáticamente en trabajo ejecutado." action={<button className="button button-outline" onClick={()=>navigate('/maintenance')}><Plus size={15}/> From recommendation</button>}/>
  <div className="planning-stats">{counts.map(c=><button key={c.status} className={`planning-stat ${filter===c.status?'selected':''}`} onClick={()=>setFilter(filter===c.status?'ALL':c.status)}><span>{c.status.replaceAll('_',' ')}</span><b>{c.count}</b></button>)}</div>
  <section className="panel planning-panel"><div className="table-toolbar"><div><b>Work order register</b><span>Transitions are recorded in the audit trail</span></div><div className="table-filter-buttons"><button className={filter==='ALL'?'selected':''} onClick={()=>setFilter('ALL')}>All</button><button className={filter==='OPEN'?'selected':''} onClick={()=>setFilter('OPEN')}>Open only</button></div></div>
   {rows.length? <div className="workorder-list">{rows.map(wo=><WorkOrderRow key={wo.id} order={wo} expanded={expanded===wo.id} history={history.data||[]} onExpand={()=>setExpanded(expanded===wo.id?null:wo.id)} onUpdate={(body)=>mutation.mutate({id:wo.id,body})} pending={mutation.isPending}/>)}</div>:<EmptyState title="No work orders in this view" description="Create a draft from a maintenance recommendation, then approve and schedule it here."/>}
  </section>
  <div className="planning-note"><Clock3 size={16}/><span><b>Scheduling policy:</b> no repair dates are generated. A user must explicitly approve an order, choose its date and transition it to SCHEDULED.</span></div>
 </>
}
function WorkOrderRow({order,expanded,history,onExpand,onUpdate,pending}:{order:WorkOrder;expanded:boolean;history:any[];onExpand:()=>void;onUpdate:(body:unknown)=>void;pending:boolean}){
 const [date,setDate]=useState(order.scheduled_date||'');const [responsible,setResponsible]=useState(order.responsible||'');const [notes,setNotes]=useState(order.observations||'')
 const progress=['PENDING','APPROVED','SCHEDULED','IN_PROGRESS','COMPLETED'].indexOf(order.status)
  return <article className={`workorder-card wo-${order.status.toLowerCase()}`}><div className="wo-main-row"><div className="wo-priority"><PriorityBadge priority={order.priority}/></div><div className="wo-title"><div><span className="wo-id">WO-{String(order.id).padStart(4,'0')}</span><b>{order.point} · {order.intervention_type}</b></div><p>{order.description}</p><div className="wo-meta"><span>Created {new Date(order.created_at).toLocaleDateString('es-CO')}</span>{order.scheduled_date&&<span><CalendarDays size={12}/> {order.scheduled_date}</span>}{order.responsible&&<span>Responsible: {order.responsible}</span>}<span className={`wo-status status-${order.status.toLowerCase()}`}>{order.status.replaceAll('_',' ')}</span></div></div><div className="wo-actions">{order.status==='PENDING'&&<button className="button button-primary button-small" onClick={()=>onUpdate({status:'APPROVED',status_note:'Approved by user'})} disabled={pending}><Check size={13}/>Approve</button>}{order.status==='APPROVED'&&<><input aria-label="Scheduled date" type="date" value={date} onChange={e=>setDate(e.target.value)}/><button className="button button-primary button-small" disabled={!date||pending} onClick={()=>onUpdate({status:'SCHEDULED',scheduled_date:date,status_note:'Scheduled by user'})}><CalendarDays size={13}/>Schedule</button></>}{order.status==='SCHEDULED'&&<button className="button button-primary button-small" disabled={pending} onClick={()=>onUpdate({status:'IN_PROGRESS',status_note:'Work started'})}><Play size={13}/>Start</button>}{order.status==='IN_PROGRESS'&&<button className="button button-primary button-small" disabled={pending} onClick={()=>onUpdate({status:'COMPLETED',status_note:'Work closed by user'})}><Check size={13}/>Complete</button>}{!['COMPLETED','CANCELED'].includes(order.status)&&<button className="icon-button danger-icon" title="Cancel order" disabled={pending} onClick={()=>window.confirm('Cancel this work order? This action is audited.')&&onUpdate({status:'CANCELED',status_note:'Canceled by user'})}><X size={16}/></button>}<button className="icon-button" title="Show audit history" onClick={onExpand}><ClipboardList size={15}/></button></div></div>
  <div className="wo-progress">{['PENDING','APPROVED','SCHEDULED','IN_PROGRESS','COMPLETED'].map((step,i)=><div key={step} className={`${i<=progress?'reached':''} ${i===progress?'now':''}`}><i/>{step.replaceAll('_',' ')}</div>)}</div>
  {expanded&&<div className="wo-expanded"><div className="wo-update-fields"><label>Responsible<input value={responsible} onChange={e=>setResponsible(e.target.value)} placeholder="Assign responsible person"/></label><label>Observations<textarea rows={2} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Execution notes, close-out details…"/></label><button className="button button-outline button-small" onClick={()=>onUpdate({responsible:responsible||null,observations:notes||null})}>Save details</button></div><div className="audit-history"><b>Status history</b>{history.length?history.map((h,i)=><div key={i}><time>{new Date(h.changed_at).toLocaleString('es-CO')}</time><span>{h.from_status||'—'} <ArrowRight size={12}/> {h.to_status}</span><small>{h.notes||'—'}</small></div>):<small>Loading or no status history.</small>}</div></div>}
 </article>
}
