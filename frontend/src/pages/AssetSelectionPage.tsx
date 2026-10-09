import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Truck } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { HitachiTruckViewer } from '../components/HitachiTruckViewer'

export function AssetSelectionPage() {
  const navigate = useNavigate()

  return <>
    <PageHeader
      eyebrow="ACTIVE ASSET · EQUIPMENT SELECTOR"
      title="Select equipment"
      description="Review the EH4000 visual model, then select EH4-01 to open its current Overview."
      action={<button className="button button-outline" onClick={() => navigate(-1)}><ArrowLeft size={15}/> Back</button>}
    />

    <div className="asset-selection-layout">
      <section className="panel asset-preview-panel">
        <div className="asset-preview-heading">
          <div><span className="eyebrow">3D ASSET PREVIEW</span><h2>Hitachi EH4000 AC3 · visual model</h2></div>
          <span className="asset-format-pill">FS25 I3D · GLB</span>
        </div>
        <div className="asset-selection-viewer"><HitachiTruckViewer/></div>
        <div className="asset-model-disclaimer"><AlertTriangle size={15}/><span><b>Visual context only:</b> converted from the supplied FS25 mod. It is not validated engineering geometry and must not be used to place SD inspection points; use the dedicated suspension STL for that.</span></div>
        <div className="asset-source-link"><span>Source: FSM_Hitachi_EH4000_FS25 · mod author listed as FS Miner</span><span>Local static GLB conversion</span></div>
      </section>

      <aside className="panel asset-selection-details">
        <span className="eyebrow">AVAILABLE EQUIPMENT</span>
        <div className="asset-option-mark"><Truck size={23}/></div>
        <h2>EH4-01</h2>
        <p className="asset-option-name">EH4000 Mining Truck</p>
        <div className="asset-option-status"><i/><span>Local historical dataset</span></div>
        <div className="asset-option-divider"/>
        <div className="asset-option-meta"><span>MANUFACTURER</span><b>Hitachi</b></div>
        <div className="asset-option-meta"><span>INSPECTION SCOPE</span><b>Front suspension · SD-01 to SD-04</b></div>
        <div className="asset-option-meta"><span>TECHNICAL MODEL</span><b>Front suspension STL · SD-01 to SD-04</b></div>
        <div className="asset-option-callout"><CheckCircle2 size={15}/><span>Historical inspection data and the existing Overview are ready for this equipment. SD condition coloring remains on its dedicated technical suspension model.</span></div>
        <button className="button button-outline asset-technical-model" onClick={() => navigate('/structural-3d')}>Open SD technical model <ArrowRight size={14}/></button>
        <button className="button button-primary asset-open-overview" onClick={() => navigate('/')}>
          Select EH4-01 · Open Overview <ArrowRight size={16}/>
        </button>
      </aside>
    </div>
  </>
}
