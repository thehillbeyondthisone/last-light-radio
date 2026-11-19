import { useEffect, useState } from 'react'
import { api, encodeFile } from './api'
export type ReferenceImage = {id:string;label:string;width:number;height:number;media_url:string;source:{sha256:string};provenance:Record<string,unknown>}
export type ReferenceSource = {id:string;label:string;frame:number;frame_count:number}|null
type Slot = 'first'|'last'
/** First / last reference frames as two picture slots. Click a slot to choose it, then Capture or Import fills that slot.
 *  No library dropdowns (Boden 2026-11-17): a slot is filled only by capturing the Viewer frame or importing an image, so what you see is what is used. */
export default function FilmReferences({first,last,onChange,disabled,source,lastTested}:{first:string;last:string;onChange:(first:string,last:string)=>void;disabled:boolean;source:ReferenceSource;lastTested:boolean}) {
 const [images,setImages]=useState<ReferenceImage[]>([])
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState('')
 const [role,setRole]=useState<Slot>(()=>first&&!last?'last':'first')
 async function refresh(){const r=await api<{images:ReferenceImage[]}>('film/images');setImages(r.images)}
 useEffect(()=>{void refresh().catch(e=>setError(String(e)))},[])
 async function act(work:()=>Promise<ReferenceImage>){if(busy)return;setBusy(true);setError('');try{const image=await work();await refresh();onChange(role==='first'?image.id:first,role==='last'?image.id:last);if(role==='first'&&!last)setRole('last')}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 const frame=source?Math.min(source.frame_count-1,Math.max(0,source.frame)):0
 const name=(s:Slot)=>s==='first'?'First frame':'Last frame'
 return <fieldset className="reference-picker" disabled={disabled||busy}><legend>Reference frames</legend>
 <div role="radiogroup" aria-label="Import into reference slot" className="reference-slots">{(['first','last'] as const).map(slot=>{const id=slot==='first'?first:last;const item=images.find(i=>i.id===id)
  // Clicking anywhere on the slot picks it; the radio keeps its plain "First frame" / "Last frame" name.
  return <div key={slot} className="reference-slot" data-selected={role===slot||undefined} onClick={e=>{if(!(e.target as HTMLElement).closest('button'))setRole(slot)}}>
   <label><input type="radio" name="reference-slot" checked={role===slot} onChange={()=>setRole(slot)}/>{name(slot)}</label>{slot==='last'&&!lastTested?<small className="reference-exp"> experimental</small>:null}
   <span className="reference-pic">{item?<img src={item.media_url} alt={`${slot} frame: ${item.label}`}/>:<span className="reference-empty">{id?'Unavailable, clear it':role===slot?'Capture or import below':'Empty'}</span>}</span>
   <div className="reference-slot-foot"><span title={item?.label}>{item?item.label:id?'Unavailable reference':'None'}</span>{id?<button type="button" aria-label={`Clear ${slot}-frame reference`} onClick={()=>onChange(slot==='first'?'':first,slot==='last'?'':last)}>Clear</button>:null}</div>
  </div>})}</div>
 <div className="reference-actions">
  <button type="button" disabled={!source} title={source?`Uses frame ${frame} of “${source.label}” as the ${name(role).toLowerCase()}`:'Open a video in the Viewer (Video tab) and park on the frame you want'} onClick={()=>{if(source)void act(()=>api<ReferenceImage>('film/images/from-frame',{video_asset_id:source.id,frame,label:`${source.label} - frame ${frame}`}))}}>Capture selected Viewer frame</button>
  <label className="reference-import">Import reference image<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;void act(async()=>{if(file.size>20*1024*1024)throw new Error('Choose an image under 20 MiB (up to 16 megapixels).');return api<ReferenceImage>('film/images/import',{filename:file.name,label:file.name,image_base64:await encodeFile(file),provenance:{kind:'user_reference_upload'}})})}}/></label>
  <span className="reference-into">into the <strong>{name(role).toLowerCase()}</strong> slot</span>
 </div>
 <p className="reference-hint">{source?<>Viewer: {source.label} · frame {frame} ({(frame/24).toFixed(2)}s)</>:'To capture, open a video in the Viewer and park on the frame you want.'}{busy?' · Saving reference…':''}</p>
 {error?<p role="alert">{error}</p>:null}
 <details className="reference-details"><summary>Reference details</summary>
  <p>Images are frozen with the take and upload to the worker only when you click Generate. Frame numbers are the Film 24 fps source clock.</p>
  {!lastTested?<p>Last-frame conditioning is experimental: its wiring is supported, but an end-to-end result has not been verified for this recipe.</p>:null}
  {(['first','last'] as const).map(slot=>{const item=images.find(i=>i.id===(slot==='first'?first:last));return item?<div key={slot}><strong>{name(slot)}:</strong> {item.label} · {item.width} × {item.height}<br/><code>{item.source.sha256}</code><pre>{JSON.stringify(item.provenance,null,2)}</pre></div>:null})}
  <button type="button" onClick={()=>void refresh().catch(e=>setError(String(e)))}>Refresh reference library</button>
 </details>
 </fieldset>
}
