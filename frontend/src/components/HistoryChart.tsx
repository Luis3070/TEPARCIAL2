import { useMemo } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import type { MaintenanceEvent } from '../types'

type HistoryRow = {date:string;hours:number;length_mm:number|null;caution_mm?:number;danger_mm?:number;severity_ratio?:number|null;margin_to_caution_mm?:number|null;margin_to_danger_mm?:number|null;structural_state:string;inspector:string;maintenance_action:string;maintenance_priority:string|null;delta_l_raw:number|null;delta_l_effective:number|null;delta_l_bridged_raw?:number|null;bridged_from_date?:string|null;bridge_null_count?:number;gap_spanning_change?:boolean;change_class:string;raw_growth_rate:number|null;effective_growth_rate:number|null;data_warning:string|null;maintenance_event_at_date:boolean}
const colors:Record<string,string>={Normal:'#3b8a4d',Alerta:'#d59d23','Crítico':'#c84238','N/I':'#8a939e'}
const fmtDate=(v:number)=>new Date(v).toLocaleDateString('es-CO',{month:'short',year:'2-digit'})

function ValueTooltip({active,payload,label,mode}:{active?:boolean;payload?:any[];label?:number;mode:string}) {
 if(!active||!payload?.length)return null
 const row=payload.find(p=>p?.payload)?.payload as HistoryRow|undefined
 if(!row)return null
 return <div className="chart-tooltip"><strong>{row.date}</strong><span>{row.hours.toLocaleString('es-CO')} h · {row.inspector}</span>
  {mode==='length'?<><b>{row.length_mm===null?'N/I':`${row.length_mm} mm`}</b><span>{row.structural_state} · Acción {row.maintenance_action.replaceAll('_',' ')}</span></>:
   <><b>{payload[0]?.value===null?'N/I':`${payload[0]?.value ?? '—'} ${mode==='growth'?'mm / 1000 h':'mm'}`}</b><span>{row.change_class.replaceAll('_',' ')}</span></>}
  {row.maintenance_event_at_date&&<em>Reparación documentada</em>}{row.gap_spanning_change&&<em>Advertencia · intervalo incompleto desde {row.bridged_from_date}: cambio puenteado {row.delta_l_bridged_raw} mm, no es ΔL consecutivo ni tasa ordinaria</em>}{row.data_warning&&!row.gap_spanning_change&&<em>Advertencia: {row.data_warning}</em>}
 </div>
}

export function HistoryChart({data,point,mode='length',axis='date',events=[],compact=false}:{data:HistoryRow[];point:string;mode?:'length'|'growth'|'severity'|'delta'|'marginC'|'marginD';axis?:'date'|'hours';events?:MaintenanceEvent[];compact?:boolean}) {
 const rows=useMemo(()=>data.map(d=>({...d,x:axis==='date'?new Date(d.date).getTime():d.hours,
  plot_value:mode==='length'?d.length_mm:mode==='growth'?d.effective_growth_rate:mode==='severity'?d.severity_ratio:mode==='delta'?d.delta_l_effective:mode==='marginC'?d.margin_to_caution_mm:d.margin_to_danger_mm,
  null_marker:d.length_mm===null?0:null})),[data,mode,axis])
 const thresholds=mode==='length'&&data[0]?[{value:(data[0] as any).caution_mm,label:'Caution',color:'#d69d22'},{value:(data[0] as any).danger_mm,label:'Danger',color:'#c84238'}]:[]
 const maxY=mode==='length'?Math.max(10,...data.map((d:any)=>d.danger_mm||0),...data.map((d:any)=>d.length_mm||0))*1.12:undefined
 const visibleEvents=[...new Map(events.map(e=>[e.date,e])).values()]
 const nulls=rows.filter(r=>r.length_mm===null)
 const dataKey='plot_value'
 const lineColor=mode==='growth'?'#dc8a3c':'#356b9b'
 const yUnit=mode==='growth'?' mm / 1000 h':mode==='severity'?' × Danger':mode==='delta'?' mm':mode.startsWith('margin')?' mm':' mm'
 return <div className={`history-chart ${compact?'chart-compact':''}`}>
  <ResponsiveContainer width="100%" height={compact?220:300}>
   <ComposedChart data={rows} margin={{top:15,right:20,left:0,bottom:4}}>
    <CartesianGrid stroke="#e8edf1" strokeDasharray="3 5" vertical={false}/>
    <XAxis dataKey="x" type="number" domain={['dataMin','dataMax']} tickFormatter={axis==='date'?fmtDate:(v:number)=>`${Math.round(v).toLocaleString('es-CO')}`} scale={axis==='date'?'time':'linear'} tick={{fontSize:11,fill:'#7b8793'}} axisLine={false} tickLine={false} minTickGap={28} label={{value:axis==='date'?'Inspection date':'Cumulative hours (h)',position:'insideBottom',offset:-1,fontSize:10,fill:'#7b8793'}}/>
    <YAxis domain={mode==='growth'||mode==='delta'||mode.startsWith('margin')?['auto','auto']:[0,maxY||'auto']} tick={{fontSize:11,fill:'#7b8793'}} axisLine={false} tickLine={false} width={50} unit={yUnit}/>
    <Tooltip content={<ValueTooltip mode={mode}/>}/>
    {thresholds.map(t=><ReferenceLine key={t.label} y={t.value} stroke={t.color} strokeDasharray="5 4" label={{value:t.label,fill:t.color,fontSize:10,position:'insideTopRight'}}/>)}
    {visibleEvents.map(e=><ReferenceLine key={`${e.date}-${point}`} x={axis==='date'?new Date(e.date).getTime():Number(data.find(d=>d.date===e.date)?.hours)} stroke="#536477" strokeDasharray="4 4" label={{value:'Reparación',position:'insideTopLeft',fill:'#536477',fontSize:9}}/>)}
    {mode==='length'&&thresholds.length===2&&<ReferenceArea y1={thresholds[0].value} y2={thresholds[1].value} fill="#d8a33d" fillOpacity={0.055}/>}
    <Line type="linear" dataKey={dataKey} stroke={lineColor} strokeWidth={2} dot={(props:any)=>{const {cx,cy,payload}=props;return <circle cx={cx} cy={cy} r={3.5} fill={colors[payload.structural_state]||'#356b9b'} stroke="#fff" strokeWidth={1.3}/>}} activeDot={{r:5}} connectNulls={false} isAnimationActive={false}/>
    {mode==='length'&&<Scatter dataKey="null_marker" shape={(props:any)=>{const {cx,cy,payload}=props;if(payload.length_mm!==null)return <g/>;return <g><circle cx={cx} cy={cy} r={5} fill="#f5f6f8" stroke="#89939d" strokeWidth={2}/><path d={`M${cx-3} ${cy+3}l6 -6`} stroke="#89939d" strokeWidth={1.5}/><text x={cx} y={cy-10} textAnchor="middle" fontSize="9" fill="#697480">N/I</text></g>}} isAnimationActive={false}/>}
   </ComposedChart>
  </ResponsiveContainer>
  {nulls.length>0&&<div className="chart-note"><i className="null-key"/> N/I: {nulls.map(n=>n.date).join(', ')} · discontinuidad conservada</div>}
 </div>
}
