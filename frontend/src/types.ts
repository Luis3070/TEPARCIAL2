export type StructuralState = 'Normal' | 'Alerta' | 'Crítico' | 'N/I'
export type ZoneState = 'NORMAL' | 'ALERT' | 'CRITICAL' | 'INCOMPLETE' | 'UNKNOWN'
export const stateSlug = (s:StructuralState|string) => s === 'Crítico' ? 'cr-tico' : s === 'N/I' ? 'n-i' : s === 'Alerta' ? 'alerta' : 'normal'

export interface Measurement {
  id: number; point: string; description: string; length_mm: number | null; caution_mm: number; danger_mm: number
  structural_state: StructuralState; severity_ratio: number | null; delta_l_raw: number | null
  delta_l_effective: number | null; change_class: string; raw_growth_rate: number | null
  effective_growth_rate: number | null; maintenance_segment: number; maintenance_action: string
  delta_l_bridged_raw?:number|null;bridged_from_date?:string|null;bridged_elapsed_hours?:number|null;bridge_null_count?:number;gap_spanning_change?:boolean
  maintenance_priority: string | null; maintenance_mode: string | null; decision_reason: string
  data_warning: string | null; comment: string | null; image_file: string | null; source_row: number | null
}
export interface Inspection {
  id: number; equipment: string; zone: string; date: string; hours: number; inspector: string
  imported: boolean; maintenance_event: boolean; measurements: Measurement[]
}
export interface Snapshot {
  date: string; hours: number; zone_state: ZoneState; worst_point: string; max_severity_ratio: number | null
  normal_count: number; alert_count: number; critical_count: number; not_inspected_count: number
  significant_growth_count: number; highest_priority: string | null; recommended_action: string
  maintenance_event: boolean; data_completeness_pct: number; inspection_id: number | null
}
export interface Recommendation {
  measurement_id: number; inspection_id: number; date: string; hours: number; point: string; description: string
  structural_state: StructuralState; length_mm: number | null; caution_mm: number; danger_mm: number
  action: string; priority: string | null; mode: string | null; reason: string; data_warning: string | null; status: string
}
export interface WorkOrder {
  id: number; equipment: string; point: string; intervention_type: string; priority: string; description: string
  status: string; created_at: string; scheduled_date: string | null; responsible: string | null
  observations: string | null; closed_at: string | null; source_measurement_id: number | null
}
export interface Point { code: string; description: string; structural_state: StructuralState; length_mm: number | null; caution_mm: number | null; danger_mm: number | null; severity_ratio?: number | null; delta_l_raw?: number|null; delta_l_effective?:number|null; delta_l_bridged_raw?:number|null; bridged_from_date?:string|null; gap_spanning_change?:boolean; raw_growth_rate?:number|null; effective_growth_rate?:number|null; change_class?:string; maintenance_segment?:number; maintenance_action?: string; maintenance_priority?: string | null; decision_reason?: string; calibration?: Calibration | null }
export interface Calibration { x:number; y:number; z:number; normal:number[]; calibrated_at:string; calibrated_by:string|null; confirmed:boolean; model_asset:string }
export interface MaintenanceEvent { id:number; date:string; hours:number|null; point:string; comment:string; event_type:string; confidence:string; source_row:number|null; source:string; classification:string }
export interface Evidence { id:number; filename:string; media_type:string; uploaded_at:string; inspection_id:number|null; work_order_id:number|null; point:string|null; notes:string|null }
