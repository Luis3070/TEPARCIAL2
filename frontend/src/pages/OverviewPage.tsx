import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Clock3, Gauge, Play, Pause, RefreshCw, ShieldCheck, Wrench } from 'lucide-react'
import { api } from '../services/api'
import { useUI } from '../state'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge, PriorityBadge } from '../components/StatusBadge'
import { HistoryChart } from '../components/HistoryChart'
import { EmptyState } from '../components/EmptyState'
import { SuspensionViewer } from '../components/SuspensionViewer'
import type { Point } from '../types'

function niceAction(x:string){return (x||'—').replaceAll('_',' ')}
export function OverviewPage(){
 const id=useUI(s=>s.selectedInspectionId);const setId=useUI(s=>s.setInspection);const point=useUI(s=>s.selectedPoint);const setPoint=useUI(s=>s.setPoint);const navigate=useNavigate()
 const summary=useQuery({queryKey:['overview',id],queryFn:()=>api.overview(id)})
 const snapshots=useQuery({queryKey:['snapshots'],queryFn:api.snapshots})
 const points=useQuery({queryKey:['points',id],queryFn:()=>api.points(id)})
 const history=useQuery({queryKey:['overview-history'],queryFn:async()=>Object.fromEntries(await Promise.all(['SD-01','SD-02','SD-03','SD-04'].map(async p=>[p,await api.pointHistory(p)])))})
 const events=useQuery({queryKey:['maintenance-events'],queryFn:api.events})
 const orders=useQuery({queryKey:['work-orders'],queryFn:()=>api.workOrders()})
 const [playing,setPlaying]=useState(false)
 const snaps=snapshots.data||[];const activeIndex=snaps.findIndex(s=>s.inspection_id===id)
 useEffect(()=>{if(!playing||!snaps.length)return;const timer=window.setInterval(()=>{const ix=snaps.findIndex(s=>s.inspection_id===id);const next=snaps[Math.min(ix+1,snaps.length-1)];if(next){setId(next.inspection_id||undefined);if(ix>=snaps.length-2)setPlaying(false)}},1800);return()=>window.clearInterval(timer)},[playing,snaps,id,setId])
 const data=summary.data;const conditionPoints=(points.data||[]) as Point[]
 const focused=conditionPoints.find(p=>p.code===point)||conditionPoints[0]
 const pointHistory=history.data?.[focused?.code||point]||[]
 const latestOrders=(orders.data||[]).filter(o=>['SCHEDULED','IN_PROGRESS'].includes(o.status)&&o.scheduled_date).sort((a,b)=>(a.scheduled_date||'').localeCompare(b.scheduled_date||''))
 const nextOrder=latestOrders[0]
 const latestDate=snaps.at(-1)?.date
 const badges=useMemo(()=>[
  {label:'NORMAL',value:data?.counts?.Normal??'—',color:'normal',icon:CheckCircle2},
  {label:'ALERT',value:data?.counts?.Alerta??'—',color:'alert',icon:AlertTriangle},
  {label:'CRITICAL',value:data?.counts?.['Crítico']??'—',color:'critical',icon:Activity},
  {label:'N/I',value:data?.counts?.['N/I']??'—',color:'unknown',icon:Clock3},
 ],[data])
 if(summary.isLoading)return <div className="page-loading"><span className="loader-ring"/> Loading asset condition…</div>
 if(summary.isError)return <div className="error-card"><AlertTriangle/><div><b>No fue posible cargar la condición.</b><span>{String(summary.error)}</span></div></div>
 return <>
  <PageHeader eyebrow="ASSET OVERVIEW · EH4-01" title="Structural Integrity" description="Suspensión delantera · Tijeras y spindle" action={<button className="button button-outline" onClick={()=>navigate('/inspections')}><ClipboardListIcon/> New inspection</button>}/>
  <div className="latest-strip"><div className="latest-strip-mark"><Clock3 size={16}/></div><div><b>Last recorded condition</b><span>{data.date} · {data.hours?.toLocaleString('es-CO')} h · {data.inspector}</span></div><span className="history-pill">HISTORICAL · NOT LIVE</span><div className="strip-spacer"/><div className="asset-zone"><span>ZONE CONDITION</span><b className={`zone-state zone-${data.zone_state?.toLowerCase()}`}>{data.zone_state?.replaceAll('_',' ')}</b></div><div className="zone-sep"/><div className="asset-zone"><span>HIGHEST ACTION</span><b>{niceAction(data.recommended_action)}</b></div><PriorityBadge priority={data.highest_priority}/></div>
  <div className="condition-kpis">{badges.map(k=>{const Icon=k.icon;return <button key={k.label} className={`condition-kpi kpi-${k.color}`} onClick={()=>navigate('/analytics')}><div className="kpi-icon"><Icon size={16}/></div><span>{k.label}</span><strong>{k.value}</strong><small>inspection points</small></button>})}<div className="condition-kpi kpi-completeness"><div className="kpi-icon"><ShieldCheck size={16}/></div><span>DATA COMPLETENESS</span><strong>{data.data_completeness_pct?.toFixed(0)}<i>%</i></strong><small>of 4 points measured</small></div><button className="condition-kpi kpi-priority" onClick={()=>navigate('/maintenance')}><div className="kpi-icon"><Wrench size={16}/></div><span>WORST POINT</span><strong>{data.worst_point}</strong><small>{focused?.description||'Highest current recommendation'}</small></button></div>
  <div className="overview-main-grid">
   <section className="panel model-panel"><div className="panel-heading"><div><span className="eyebrow">STRUCTURAL DIGITAL TWIN</span><h2>Front suspension assembly</h2></div><button className="text-button" onClick={()=>navigate('/structural-3d')}>Open 3D workspace <ArrowRight size={15}/></button></div>
    <div className="overview-model-view"><SuspensionViewer points={conditionPoints as any} selectedPoint={point} onSelect={setPoint}/><div className="model-overlay"><b>EH4000 · FRONT SUSPENSION</b><span>STL TECHNICAL MODEL · MANUAL HOTSPOT CALIBRATION</span></div></div>
    <div className="point-selector">{conditionPoints.map(p=><button key={p.code} onClick={()=>setPoint(p.code)} className={`point-chip ${point===p.code?'selected':''}`}><i className={`state-dot state-dot-${p.structural_state.replace('/','-').toLowerCase()}`}/><span><b>{p.code}</b><small>{p.length_mm===null?'N/I':`${p.length_mm} mm`}</small></span><StatusBadge state={p.structural_state}/></button>)}</div>
   </section>
   <section className="panel condition-panel"><div className="panel-heading"><div><span className="eyebrow">SELECTED POINT</span><h2>{focused?.code||'—'}</h2></div>{focused&&<StatusBadge state={focused.structural_state}/>}</div>
    {focused&&<><div className="detail-point-name">{focused.description}</div><div className="length-readout"><strong>{focused.length_mm===null?'—':focused.length_mm}</strong><span>mm <small>RAW</small></span></div><div className="severity-meter"><div><span>Severity ratio</span><b>{focused.length_mm===null?'N/I':`${((focused.length_mm/focused.danger_mm!)*100).toFixed(0)}% of Danger`}</b></div><div className="meter-track"><i style={{width:`${Math.min(100,(focused.length_mm||0)/(focused.danger_mm||1)*100)}%`,background:focused.structural_state==='Crítico'?'#c64138':focused.structural_state==='Alerta'?'#d7a322':'#438850'}}/></div></div>
    <div className="threshold-row"><div><small>CAUTION</small><b>{focused.caution_mm} mm</b></div><div><small>DANGER</small><b>{focused.danger_mm} mm</b></div><div><small>ΔL RAW</small><b>{focused.delta_l_raw??'—'} mm</b></div></div>
    <div className="recommendation-box"><div className="rec-icon"><Wrench size={16}/></div><div><span>MAINTENANCE ACTION</span><b>{niceAction(focused.maintenance_action||'')}</b><small>{focused.decision_reason||'No additional decision context.'}</small></div><PriorityBadge priority={focused.maintenance_priority??null}/></div>
    <div className="panel-actions"><button className="button button-primary" onClick={()=>navigate('/maintenance')}>Review actions <ArrowRight size={15}/></button><button className="button button-ghost" onClick={()=>navigate('/structural-3d')}>Inspect point <CrosshairIcon/></button></div></>}
    <div className="upcoming-activity">{nextOrder?<><CalendarDays size={16}/><div><span>NEXT SCHEDULED ACTIVITY · {nextOrder.scheduled_date}</span><b>{nextOrder.intervention_type} · {nextOrder.point}</b></div><PriorityBadge priority={nextOrder.priority}/></>:<><CalendarDays size={16}/><div><span>PLANNING</span><b>No work order has been scheduled.</b></div><button className="link-button" onClick={()=>navigate('/planning')}>Open planner →</button></>}</div>
   </section>
  </div>
  <section className="panel timeline-panel"><div className="timeline-header"><div><span className="eyebrow">INSPECTION HISTORY</span><h2>Condition timeline</h2><p>Discrete inspection dates only · no interpolated lengths</p></div><div className="timeline-readout"><div><span>SELECTED INSPECTION</span><b>{data.date}</b></div><div><span>OPERATING HOURS</span><b>{data.hours?.toLocaleString('es-CO')} h</b></div></div></div>
   <div className="timeline-track-wrap"><button className="round-control" disabled={activeIndex<=0} onClick={()=>setId(snaps[activeIndex-1]?.inspection_id||undefined)}><ChevronLeft size={18}/></button><div className="timeline-range-area"><input aria-label="Inspection timeline" type="range" min={0} max={Math.max(0,snaps.length-1)} value={activeIndex<0?snaps.length-1:activeIndex} onChange={e=>setId(snaps[Number(e.target.value)]?.inspection_id||undefined)} style={{'--range-progress':`${snaps.length>1?Math.max(0,activeIndex)/(snaps.length-1)*100:100}%`} as CSSProperties}/><div className="timeline-dots">{snaps.map((s,i)=><button title={`${s.date}: ${s.zone_state}`} key={s.date} onClick={()=>setId(s.inspection_id||undefined)} className={`timeline-dot zone-${s.zone_state.toLowerCase()} ${s.maintenance_event?'has-event':''} ${i===activeIndex?'current':''}`} style={{left:`${snaps.length>1?i/(snaps.length-1)*100:0}%`}}/> )}</div><div className="timeline-axis"><span>{snaps[0]?.date}</span><span>{snaps.at(-1)?.date}</span></div></div><button className="round-control" disabled={activeIndex>=snaps.length-1} onClick={()=>setId(snaps[activeIndex+1]?.inspection_id||undefined)}><ChevronRight size={18}/></button><button className={`round-control play-control ${playing?'is-playing':''}`} onClick={()=>setPlaying(v=>!v)}>{playing?<Pause size={16}/>:<Play size={16}/>}</button><button className="round-control" title="Reset to latest" onClick={()=>{setPlaying(false);setId(snaps.at(-1)?.inspection_id||undefined)}}><RefreshCw size={15}/></button></div>
   <div className="timeline-legend"><span><i className="legend-normal"/>Normal</span><span><i className="legend-alert"/>Alert</span><span><i className="legend-critical"/>Critical</span><span><i className="legend-incomplete"/>Incomplete</span><span><i className="legend-event"/>Documented repair</span><small>Each marker represents a recorded inspection.</small></div>
  </section>
  <div className="overview-chart-grid"><section className="panel chart-panel"><div className="panel-heading"><div><span className="eyebrow">CRACK DEVELOPMENT</span><h2>{focused?.code} · Length over time</h2></div><button className="text-button" onClick={()=>navigate('/analytics')}>Open analytics <ArrowRight size={14}/></button></div>{pointHistory.length?<HistoryChart data={pointHistory} point={focused?.code||point} mode="length" events={events.data||[]} compact/>:<EmptyState title="History unavailable"/>}</section><section className="panel action-queue"><div className="panel-heading"><div><span className="eyebrow">CURRENT RECOMMENDATIONS</span><h2>Maintenance actions</h2></div><button className="text-button" onClick={()=>navigate('/maintenance')}>View all <ArrowRight size={14}/></button></div><div className="queue-list">{conditionPoints.slice().sort((a,b)=>(b.maintenance_priority||'').localeCompare(a.maintenance_priority||'')).map(p=><button key={p.code} className="queue-item" onClick={()=>{setPoint(p.code);navigate('/maintenance')}}><div className={`queue-mark ${p.structural_state==='Crítico'?'critical':p.structural_state==='Alerta'?'alert':p.structural_state==='N/I'?'unknown':'normal'}`}/><div className="queue-copy"><b>{p.code}<span>{niceAction(p.maintenance_action||'')}</span></b><small>{p.length_mm===null?'Measurement unavailable':`${p.length_mm} mm · ${p.structural_state}`}</small></div><PriorityBadge priority={p.maintenance_priority??null}/><ArrowRight size={14}/></button>)}</div><div className="queue-footer"><span>Recommendations are not approved or executed work orders.</span><button onClick={()=>navigate('/planning')}>Go to planner</button></div></section></div>
 </>
}

function ClipboardListIcon(){return <ClipboardIcon/>}function ClipboardIcon(){return <Activity size={15}/>}function CrosshairIcon(){return <Gauge size={15}/>}
