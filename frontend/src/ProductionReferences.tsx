import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { ReferenceImage } from './FilmReferences'
export type ProductionBinding = { id: string; revision: number; view: string }
type VisualView = { name: string; image_id: string; description: string }
type VisualReference = { id: string; revision: number; kind: 'character'|'location'|'prop'; label: string; guidelines: string; views: VisualView[] }
export type ReferenceInput = { image_id: string; role: string }
type Compiled = { brief: string; first_frame_id: string|null; last_frame_id: null; production_reference_bindings: ProductionBinding[]; reference_images?: ReferenceInput[]; recipe_id?:string|null }
const bindingKey=(b:ProductionBinding)=>JSON.stringify([b.id,b.revision,b.view])
export default function ProductionReferences({projectId,shotId,brief,bindings,multiImage=false,disabled,onApply}:{projectId:string;shotId:string;brief:string;bindings:ProductionBinding[];multiImage?:boolean;disabled:boolean;onApply:(c:Compiled)=>void}) {
 const [records,setRecords]=useState<VisualReference[]>([]),[images,setImages]=useState<ReferenceImage[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const [editing,setEditing]=useState<VisualReference|null>(null),[label,setLabel]=useState(''),[kind,setKind]=useState<VisualReference['kind']>('location'),[guidelines,setGuidelines]=useState(''),[views,setViews]=useState<VisualView[]>([])
 const [selected,setSelected]=useState<ProductionBinding[]>([]),[condition,setCondition]=useState(''),[action,setAction]=useState('')
 const [mode,setMode]=useState<'first_frame'|'reference_images'>(multiImage?'reference_images':'first_frame')
 const active=useRef({projectId,shotId}); active.current={projectId,shotId}
 const route=`film/projects/${projectId}/references`
 async function refresh(){const [r,i]=await Promise.all([api<{references:VisualReference[]}>(route),api<{images:ReferenceImage[]}>('film/images')]);if(active.current.projectId===projectId){setRecords(r.references);setImages(i.images)}}
 useEffect(()=>{setRecords([]);setError('');edit(null);if(projectId)void refresh().catch(e=>setError(e.message))},[projectId])
 useEffect(()=>{setSelected(bindings);setCondition(bindings[0]?bindingKey(bindings[0]):'');setMode(multiImage?'reference_images':'first_frame');setAction(brief.split('\n\nVisual continuity guidelines:')[0])},[shotId,brief,multiImage,JSON.stringify(bindings)])
 async function work(fn:()=>Promise<void>){if(busy)return;setBusy(true);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 function edit(r:VisualReference|null){setEditing(r);setLabel(r?.label??'');setKind(r?.kind??'location');setGuidelines(r?.guidelines??'');setViews(r?.views??[])}
 return <details className="fcp-production-references"><summary>Production references · characters / locations / props</summary>
 <p>Reusable visual definitions for this project. Shots pin a revision; changing a definition never silently changes existing takes.</p>
 {error?<p role="alert">{error}</p>:null}
 <button type="button" disabled={busy||!projectId} onClick={()=>void work(refresh)}>Refresh production references</button>
 <fieldset disabled={busy||disabled||!projectId}><legend>Reference bin</legend>
 {records.map(r=>{const pinned=selected.filter(b=>b.id===r.id&&b.revision!==r.revision);return <article key={r.id}><strong>{r.kind}: {r.label} · v{r.revision}</strong>
 <button type="button" onClick={()=>edit(r)}>Edit definition</button><p>{r.guidelines}</p>
 {pinned.map(b=><p key={bindingKey(b)}>Pinned {b.view} · v{b.revision}. <button type="button" onClick={()=>setSelected(selected.filter(x=>bindingKey(x)!==bindingKey(b)))}>Remove pinned view</button></p>)}
 {r.views.map(v=>{const binding={id:r.id,revision:r.revision,view:v.name},key=bindingKey(binding),checked=selected.some(b=>bindingKey(b)===key);return <figure key={v.name} style={{display:'inline-block',margin:4,maxWidth:150}}><img src={`/api/film/images/${v.image_id}/media`} alt={`${r.label}: ${v.name}`} style={{maxWidth:140,maxHeight:100,objectFit:'contain'}}/><figcaption><label><input type="checkbox" checked={checked} disabled={!checked&&selected.length>=9} onChange={e=>{setSelected(e.target.checked?[...selected,binding]:selected.filter(b=>bindingKey(b)!==key));if(e.target.checked&&!condition)setCondition(key)}}/>{v.name}</label></figcaption></figure>})}</article>})}
 {!records.length?<p>No definitions yet. Import or capture images in the Generate tab, then create a definition here.</p>:null}
 <details><summary>{editing?'Revise definition':'Create definition'}</summary><button type="button" onClick={()=>edit(null)}>New definition</button>
 <label>Name<input value={label} onChange={e=>setLabel(e.target.value)} maxLength={200}/></label><label>Kind<select value={kind} onChange={e=>setKind(e.target.value as VisualReference['kind'])}><option value="character">Character</option><option value="location">Location</option><option value="prop">Prop</option></select></label>
 <label>Fixed visual guidelines<textarea value={guidelines} onChange={e=>setGuidelines(e.target.value)} maxLength={2000} placeholder="Appearance, fixed objects, layout, permitted changes"/></label>
 {views.map((v,n)=><div key={n}><label>View name<input value={v.name} onChange={e=>setViews(views.map((x,k)=>k===n?{...x,name:e.target.value}:x))}/></label><label>Immutable source image<select value={v.image_id} onChange={e=>setViews(views.map((x,k)=>k===n?{...x,image_id:e.target.value}:x))}><option value="">Choose imported image</option>{images.map(i=><option key={i.id} value={i.id}>{i.label}</option>)}</select></label><label>What this view establishes<input value={v.description} onChange={e=>setViews(views.map((x,k)=>k===n?{...x,description:e.target.value}:x))} placeholder="Face identity, clothing, room layout..." maxLength={1000}/></label><button type="button" onClick={()=>setViews(views.filter((_,k)=>k!==n))}>Remove view</button></div>)}
 <button type="button" onClick={()=>setViews([...views,{name:'',image_id:'',description:''}])}>Add named view</button>
 <button type="button" disabled={!label.trim()||!guidelines.trim()||!views.length||views.some(v=>!v.name.trim()||!v.image_id)} onClick={()=>void work(async()=>{const r=await api<VisualReference>(route,{id:editing?.id,expected_revision:editing?.revision??0,kind,label,guidelines,views});if(active.current.projectId===projectId)edit(r);await refresh()})}>Save definition revision</button></details>
 </fieldset>
 <fieldset disabled={busy||disabled||!shotId}><legend>Use in selected planned shot</legend>
 <p>{bindings.length?`${bindings.length} reference definition(s) attached to this shot draft.`:'No saved reference bindings on this shot.'}</p>
 <label>Action and camera direction<textarea value={action} onChange={e=>setAction(e.target.value)} maxLength={2000}/></label>
 <label>Image conditioning<select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="first_frame">One first-frame anchor + text guidelines</option><option value="reference_images">Multiple visual references (experimental H3 R2V)</option></select></label>
 {mode==='first_frame'?<><label>Actual H3 first-frame image<select value={condition} onChange={e=>setCondition(e.target.value)}><option value="">Choose one selected view</option>{selected.map(b=><option key={bindingKey(b)} value={bindingKey(b)}>{records.find(r=>r.id===b.id)?.label??b.id} · {b.view} · v{b.revision}</option>)}</select></label><p>Only this view is image-conditioned. Other views supply text guidelines.</p></>:<><p>{selected.length}/9 images, in conditioning order. Every selected view is sent to H3 with its character, location or prop role. These are appearance references, not first/last frames. This experimental route must be evaluated with the installed model; additional images do not guarantee better consistency.</p><ol>{selected.map(b=><li key={bindingKey(b)}>{records.find(r=>r.id===b.id)?.label??b.id}: {b.view} · v{b.revision}</li>)}</ol></>}
 <p>References reduce drift but do not guarantee identity or a consistent 3D space. Review each generated take.</p>
 <button type="button" disabled={!action.trim()||!selected.length||selected.length>9||(mode==='first_frame'&&!selected.some(b=>bindingKey(b)===condition))} onClick={()=>void work(async()=>{const binding=selected.find(b=>bindingKey(b)===condition);const c=await api<Compiled>(route+'/compile',{bindings:selected,conditioning_mode:mode,conditioning_reference_id:binding?.id,conditioning_binding:binding,action});if(active.current.projectId===projectId&&active.current.shotId===shotId)onApply({...c,reference_images:c.reference_images??[],recipe_id:c.recipe_id??null})})}>Apply references to shot draft</button>
 <p>Then Save shot plan and Prepare generation. Selected images and pinned definitions travel with that take; no render starts here.</p>
 </fieldset></details>
}
