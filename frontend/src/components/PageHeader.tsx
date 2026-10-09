export function PageHeader({eyebrow,title,description,action}:{eyebrow:string;title:string;description?:string;action?:React.ReactNode}) {
 return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description&&<p>{description}</p>}</div>{action&&<div className="page-header-action">{action}</div>}</div>
}
