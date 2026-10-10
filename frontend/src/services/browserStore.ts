import type { Evidence, Inspection, MaintenanceEvent, Measurement, Point, Recommendation, Snapshot, WorkOrder } from '../types'

const KEY = 'eh4000-evaluation-records-v1'
const POINTS = ['SD-01', 'SD-02', 'SD-03', 'SD-04'] as const
type PointCode = typeof POINTS[number]
type NewInspection = { equipment: string; date: string; hours: number; inspector: string; measurements: {point: PointCode; length_mm: number|null; comment?: string|null; maintenance_event?: boolean}[] }
type NewOrder = {point: PointCode; priority: string; intervention_type: string; description: string; source_measurement_id?: number|null}
type AuditRow = {from_status:string|null;to_status:string;changed_at:string;notes:string|null}
type Store = {inspections:Inspection[];orders:WorkOrder[];audit:Record<string,AuditRow[]>;evidence:Evidence[]}

function read():Store {
  try { const value=JSON.parse(localStorage.getItem(KEY)||'null') as Store|null; if(value&&Array.isArray(value.inspections)&&Array.isArray(value.orders)&&Array.isArray(value.evidence))return value } catch { /* treat an invalid record as empty */ }
  return {inspections:[],orders:[],audit:{},evidence:[]}
}
function write(value:Store){localStorage.setItem(KEY,JSON.stringify(value))}
export const browserInspections=()=>read().inspections
export const browserOrders=()=>read().orders
export const browserEvidence=()=>read().evidence
export const browserAudit=(id:number)=>read().audit[String(id)]||[]
export function browserRecordCounts(){const store=read();return {inspections:store.inspections.length,orders:store.orders.length,evidence:store.evidence.length}}
export async function clearBrowserRecords():Promise<void>{
  const db=await evidenceDb()
  try{await new Promise<void>((resolve,reject)=>{const tx=db.transaction('files','readwrite');tx.objectStore('files').clear();tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error)})}
  finally{db.close()}
  localStorage.removeItem(KEY)
}

function stateFor(length:number|null,caution:number,danger:number):Measurement['structural_state']{return length===null?'N/I':length<caution?'Normal':length<danger?'Alerta':'Crítico'}
function decide(m:Measurement,firstPostRepair:boolean,firstValid:boolean):[string,string|null,string|null,string]{
  const L=m.length_mm,c=m.caution_mm,d=m.danger_mm,change=m.change_class
  if(m.structural_state==='Crítico')return ['REPAIR_BEFORE_OPERATION','P4','CORRECTIVE_IMMEDIATE',`L = ${L} mm alcanza Danger = ${d} mm. Reparar antes de continuar operando.`]
  if(m.structural_state==='Alerta')return change==='SIGNIFICANT_GROWTH'?['PRIORITIZE_REPAIR','P3','CORRECTIVE_PRIORITY',`L = ${L} mm supera Caution = ${c} mm y creció ${m.delta_l_raw} mm desde la inspección anterior. Priorizar reparación.`]:['PLAN_REPAIR','P2','CORRECTIVE_PLANNED',`L = ${L} mm supera Caution = ${c} mm. Reparación programable.`]
  if(m.structural_state==='N/I')return ['REINSPECTION_REQUIRED','P1','INSPECTION','Medición no disponible. Condición estructural no evaluable.']
  if(firstPostRepair)return ['POST_REPAIR_VERIFICATION','P1','INSPECTION','Primera inspección posterior a reparación documentada.']
  if(firstValid)return ['INITIAL_MEASURE',null,null,'Primera medición válida de la serie; establece línea base y no tiene ΔL previo.']
  if(change==='STABLE_WITHIN_TOLERANCE')return ['MONITOR_ROUTINE','P0','PREVENTIVE','Normal y sin cambio superior a la tolerancia de medición.']
  if(change==='SIGNIFICANT_GROWTH')return ['MONITOR_INTENSIFIED','P1','PREVENTIVE',`Normal con crecimiento significativo de ${m.delta_l_raw} mm desde la inspección anterior.`]
  if(change==='N_I'&&m.gap_spanning_change)return ['MONITOR_ROUTINE','P0','PREVENTIVE',`Estado actual Normal. ΔL consecutivo no calculable por NULL previo; cambio puenteado ${m.delta_l_bridged_raw} mm mostrado con advertencia y no usado para priorizar.`]
  return ['RULE_NOT_DEFINED',null,null,`Combinación sin regla V1 explícita: structural_state=${m.structural_state}; change_class=${change}. Revisión ingenieril requerida.`]
}
export function createBrowserInspection(body:NewInspection,source:Inspection[]):Inspection{
  const records=[...source,...browserInspections()].sort((a,b)=>b.date.localeCompare(a.date))
  const previous=records[0]
  if(body.equipment!=='EH4-01')throw Error('Solo se admite EH4-01.')
  if(!/^\d{4}-\d{2}-\d{2}$/.test(body.date)||!Number.isFinite(Date.parse(body.date)))throw Error('Fecha de inspección inválida.')
  if(records.some(row=>row.date===body.date))throw Error('Ya existe una inspección para este equipo y fecha; no se sobrescriben históricos.')
  if(previous&&body.date<=previous.date)throw Error(`La nueva inspección debe ser posterior a la última fecha (${previous.date}).`)
  if(!Number.isFinite(body.hours)||body.hours<0||(previous&&body.hours<previous.hours))throw Error('El horómetro no puede ser menor que el último registrado.')
  if(!body.inspector?.trim()||body.inspector.trim().length>80)throw Error('Indica un inspector válido.')
  if(body.measurements.length!==4||new Set(body.measurements.map(m=>m.point)).size!==4||body.measurements.some(m=>!POINTS.includes(m.point)))throw Error('Se requieren los cuatro puntos SD una sola vez.')
  if(body.measurements.some(m=>m.length_mm!==null&&(!Number.isFinite(m.length_mm)||m.length_mm<0||m.length_mm>10000)))throw Error('Longitud inválida; usa N/I cuando no exista medición.')
  const id=Math.max(0,...records.map(x=>x.id))+1
  const maxMeasurement=Math.max(0,...records.flatMap(x=>x.measurements.map(m=>m.id)))
  const allAscending=[...records].reverse()
  const measurements=POINTS.map((code,index)=>{
    const input=body.measurements.find(m=>m.point===code)!
    const prev=previous?.measurements.find(m=>m.point===code)
    const template=prev||source[0].measurements.find(m=>m.point===code)!
    const length=input.length_mm,comment=input.comment?.trim()||null
    const repair=Boolean(input.maintenance_event||comment&&/repar|soldad|interven|cambio|reparación general/i.test(comment))
    const delta=length!==null&&prev?.length_mm!==null&&prev?.length_mm!==undefined?length-prev.length_mm:null
    const effective=delta===null?null:Math.abs(delta)<=10?0:delta
    let change='N_I',rawRate:number|null=null,effectiveRate:number|null=null,warning:string|null=length===null?'CURRENT_MEASUREMENT_NULL':null
    let bridged:number|null=null,bridgedFrom:string|null=null,bridgedHours:number|null=null,nullCount=0,gap=false
    if(length!==null&&prev){
      if(prev.length_mm===null){
        warning='PREVIOUS_MEASUREMENT_NULL'
        const prior=[...allAscending].reverse().find(i=>i.measurements.find(m=>m.point===code)?.length_mm!==null)
        const priorValue=prior?.measurements.find(m=>m.point===code)?.length_mm
        if(prior&&priorValue!==null&&priorValue!==undefined&&!repair){gap=true;bridged=length-priorValue;bridgedFrom=prior.date;bridgedHours=body.hours-prior.hours;nullCount=allAscending.filter(i=>i.date>prior.date&&i.date<body.date&&i.measurements.find(m=>m.point===code)?.length_mm===null).length;warning='GAP_SPANNING_CHANGE'}
      }else if(repair)change='MAINTENANCE_RESET'
      else {change=Math.abs(delta!)<=10?'STABLE_WITHIN_TOLERANCE':delta!>10?'SIGNIFICANT_GROWTH':'SIGNIFICANT_DECREASE_REVIEW';const dh=body.hours-previous.hours;if(dh>0){rawRate=delta!/dh*1000;effectiveRate=Math.abs(delta!)<=10?0:rawRate}}
    }else if(length!==null&&!prev)warning='INITIAL_MEASURE'
    const m:Measurement={id:maxMeasurement+index+1,point:code,description:template.description,length_mm:length,caution_mm:template.caution_mm,danger_mm:template.danger_mm,structural_state:stateFor(length,template.caution_mm,template.danger_mm),severity_ratio:length===null?null:length/template.danger_mm,delta_l_raw:delta,delta_l_effective:effective,change_class:change,raw_growth_rate:rawRate,effective_growth_rate:effectiveRate,maintenance_segment:(prev?.maintenance_segment||0)+(repair?1:0),maintenance_action:'',maintenance_priority:null,maintenance_mode:null,decision_reason:'',data_warning:warning,comment,image_file:null,source_row:null,delta_l_bridged_raw:bridged,bridged_from_date:bridgedFrom,bridged_elapsed_hours:bridgedHours,bridge_null_count:nullCount,gap_spanning_change:gap}
    const firstValid=length!==null&&!allAscending.some(i=>i.measurements.find(m=>m.point===code)?.length_mm!==null)
    const [action,priority,mode,reason]=decide(m,repair||Boolean(previous?.maintenance_event),firstValid)
    return {...m,maintenance_action:action,maintenance_priority:priority,maintenance_mode:mode,decision_reason:reason}
  })
  const row:Inspection={id,equipment:'EH4-01',zone:previous?.zone||'Tijeras y spindle (suspensión delantera)',date:body.date,hours:body.hours,inspector:body.inspector.trim(),imported:false,maintenance_event:body.measurements.some(m=>Boolean(m.maintenance_event||m.comment&&/repar|soldad|interven|cambio|reparación general/i.test(m.comment))),measurements}
  const store=read();store.inspections.unshift(row);write(store);return row
}
export function recommendationFor(i:Inspection):Recommendation[]{return i.measurements.map(m=>({measurement_id:m.id,inspection_id:i.id,date:i.date,hours:i.hours,point:m.point,description:m.description,structural_state:m.structural_state,length_mm:m.length_mm,caution_mm:m.caution_mm,danger_mm:m.danger_mm,action:m.maintenance_action,priority:m.maintenance_priority,mode:m.maintenance_mode,reason:m.decision_reason,data_warning:m.data_warning,status:'RECOMMENDED_NOT_ORDERED'}))}
export function snapshotFor(i:Inspection):Snapshot{
  const m=i.measurements,normal=m.filter(x=>x.structural_state==='Normal').length,alert=m.filter(x=>x.structural_state==='Alerta').length,critical=m.filter(x=>x.structural_state==='Crítico').length,ni=m.filter(x=>x.structural_state==='N/I').length
  const rank=(p:string|null)=>Number(p?.slice(1)||-1)
  const worst=[...m].sort((a,b)=>rank(b.maintenance_priority)-rank(a.maintenance_priority)||(b.severity_ratio||0)-(a.severity_ratio||0)||b.point.localeCompare(a.point))[0]
  return {date:i.date,hours:i.hours,zone_state:critical?'CRITICAL':alert?'ALERT':ni?'INCOMPLETE':'NORMAL',worst_point:worst.point,max_severity_ratio:Math.max(...m.map(x=>x.severity_ratio||0)),normal_count:normal,alert_count:alert,critical_count:critical,not_inspected_count:ni,significant_growth_count:m.filter(x=>x.change_class==='SIGNIFICANT_GROWTH').length,highest_priority:worst.maintenance_priority,recommended_action:worst.maintenance_action,maintenance_event:i.maintenance_event,data_completeness_pct:(4-ni)/4*100,inspection_id:i.id}
}
export function overviewFor(i:Inspection,template:any){const snap=snapshotFor(i);return {...template,inspection_id:i.id,date:i.date,hours:i.hours,inspector:i.inspector,counts:{Normal:snap.normal_count,Alerta:snap.alert_count,'Crítico':snap.critical_count,'N/I':snap.not_inspected_count},zone_state:snap.zone_state,worst_point:snap.worst_point,highest_priority:snap.highest_priority,recommended_action:snap.recommended_action,data_completeness_pct:snap.data_completeness_pct,points:recommendationFor(i).map(r=>({...r,margin_to_caution_mm:r.length_mm===null?null:r.caution_mm-r.length_mm,margin_to_danger_mm:r.length_mm===null?null:r.danger_mm-r.length_mm,severity_ratio:r.length_mm===null?null:r.length_mm/r.danger_mm}))}}
export function pointsFor(i:Inspection,template:Point[]):Point[]{return i.measurements.map(m=>{const p=template.find(x=>x.code===m.point)!;return {...p,structural_state:m.structural_state,length_mm:m.length_mm,severity_ratio:m.severity_ratio,delta_l_raw:m.delta_l_raw,delta_l_effective:m.delta_l_effective,delta_l_bridged_raw:m.delta_l_bridged_raw,bridged_from_date:m.bridged_from_date,gap_spanning_change:m.gap_spanning_change,raw_growth_rate:m.raw_growth_rate,effective_growth_rate:m.effective_growth_rate,change_class:m.change_class,maintenance_segment:m.maintenance_segment,maintenance_action:m.maintenance_action,maintenance_priority:m.maintenance_priority,decision_reason:m.decision_reason}})}
export function createBrowserOrder(body:NewOrder,validMeasurements:Measurement[]):WorkOrder{
  if(!POINTS.includes(body.point)||!body.intervention_type?.trim()||!body.description?.trim())throw Error('Completa el punto, la intervención y la descripción.')
  if(body.source_measurement_id&& !validMeasurements.some(m=>m.id===body.source_measurement_id&&m.point===body.point))throw Error('La medición de origen no corresponde al punto seleccionado.')
  const store=read(),id=Math.max(0,...store.orders.map(o=>o.id))+1,now=new Date().toISOString()
  const row:WorkOrder={id,equipment:'EH4-01',point:body.point,priority:body.priority,intervention_type:body.intervention_type.trim(),description:body.description.trim(),status:'PENDING',created_at:now,scheduled_date:null,responsible:null,observations:null,closed_at:null,source_measurement_id:body.source_measurement_id||null}
  store.orders.unshift(row);store.audit[String(id)]=[{from_status:null,to_status:'PENDING',changed_at:now,notes:'Orden creada; recomendación no equivale a aprobación.'}];write(store);return row
}
const transitions:Record<string,string[]>={PENDING:['APPROVED','CANCELED'],APPROVED:['SCHEDULED','CANCELED'],SCHEDULED:['IN_PROGRESS','CANCELED'],IN_PROGRESS:['COMPLETED','CANCELED'],COMPLETED:[],CANCELED:[]}
export function updateBrowserOrder(id:number,body:Partial<WorkOrder>&{status_note?:string}):WorkOrder{
  const store=read(),index=store.orders.findIndex(o=>o.id===id);if(index<0)throw Error('Orden no encontrada.')
  const current=store.orders[index],target=body.status
  if(target&&target!==current.status&&!transitions[current.status].includes(target))throw Error(`Transición inválida: ${current.status} → ${target}.`)
  if(target==='SCHEDULED'&&!body.scheduled_date&&!current.scheduled_date)throw Error('Una orden programada requiere fecha explícita.')
  const now=new Date().toISOString();const {status_note,...updates}=body
  const next={...current,...updates,closed_at:target==='COMPLETED'||target==='CANCELED'?now:current.closed_at}
  if(target&&target!==current.status)(store.audit[String(id)]??=[]).push({from_status:current.status,to_status:target,changed_at:now,notes:status_note||null})
  store.orders[index]=next;write(store);return next
}

function evidenceDb():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{const req=indexedDB.open('eh4000-evaluation-evidence',1);req.onupgradeneeded=()=>{if(!req.result.objectStoreNames.contains('files'))req.result.createObjectStore('files')};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
export async function saveBrowserEvidence(form:FormData,validInspections:Inspection[],validOrders:WorkOrder[]):Promise<Evidence>{
  const file=form.get('file');if(!(file instanceof File))throw Error('Selecciona un archivo.')
  if(!['image/jpeg','image/png','image/webp','application/pdf'].includes(file.type))throw Error('Adjunta JPG, PNG, WEBP o PDF.')
  if(file.size>20*1024*1024)throw Error('Tamaño máximo: 20 MB.')
  const inspectionId=Number(form.get('inspection_id'))||null,orderId=Number(form.get('work_order_id'))||null
  if(!inspectionId&&!orderId)throw Error('Asocia la evidencia a una inspección o una orden.')
  if(inspectionId&&!validInspections.some(i=>i.id===inspectionId))throw Error('Inspección no encontrada.')
  if(orderId&&!validOrders.some(o=>o.id===orderId))throw Error('Orden no encontrada.')
  const store=read(),id=Math.max(0,...store.evidence.map(e=>e.id))+1
  const db=await evidenceDb();await new Promise<void>((resolve,reject)=>{const tx=db.transaction('files','readwrite');tx.objectStore('files').put(file,id);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error)});db.close()
  const row:Evidence={id,filename:file.name,media_type:file.type,uploaded_at:new Date().toISOString(),inspection_id:inspectionId,work_order_id:orderId,point:String(form.get('point')||'')||null,notes:String(form.get('notes')||'')||null}
  try{store.evidence.unshift(row);write(store)}catch(error){const rollback=await evidenceDb();rollback.transaction('files','readwrite').objectStore('files').delete(id);rollback.close();throw error}
  return row
}
export async function browserEvidenceUrl(id:number):Promise<string>{const db=await evidenceDb();const file=await new Promise<Blob>((resolve,reject)=>{const req=db.transaction('files').objectStore('files').get(id);req.onsuccess=()=>req.result?resolve(req.result as Blob):reject(Error('Archivo no encontrado.'));req.onerror=()=>reject(req.error)});db.close();return URL.createObjectURL(file)}
export function browserEvents(inspections:Inspection[]):MaintenanceEvent[]{return inspections.filter(i=>!i.imported&&i.maintenance_event).flatMap(i=>i.measurements.filter(m=>m.comment&&/repar|soldad|interven|cambio|reparación general/i.test(m.comment)).map(m=>({id:m.id,date:i.date,hours:i.hours,point:m.point,comment:m.comment!,event_type:'maintenance action',confidence:'user documented',source_row:null,source:'user',classification:'MAINTENANCE_EVENT'})))}
