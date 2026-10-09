import { create } from 'zustand'

interface UIState {
  selectedInspectionId: number | undefined
  selectedPoint: string
  notice: {kind:'success'|'error';text:string}|null
  setInspection: (id:number|undefined)=>void
  setPoint: (code:string)=>void
  notify: (kind:'success'|'error',text:string)=>void
  clearNotice: ()=>void
}
export const useUI = create<UIState>((set)=>({
  selectedInspectionId: undefined, selectedPoint:'SD-01', notice:null,
  setInspection:(selectedInspectionId)=>set({selectedInspectionId}),
  setPoint:(selectedPoint)=>set({selectedPoint}),
  notify:(kind,text)=>{set({notice:{kind,text}});window.setTimeout(()=>set({notice:null}),4500)},
  clearNotice:()=>set({notice:null}),
}))
