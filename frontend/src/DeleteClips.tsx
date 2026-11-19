import {useEffect,useMemo,useState} from 'react'
import {api} from './api'

/** Remove video clips from the library, or delete their files from disk. The server refuses any clip still used by a
 *  saved sequence or shot plan; clips used by unsaved edits in this editor are refused here. A dry run fills in the
 *  usage and sizes before anything is removed. */
export type DeletableClip={id:string;label:string;status:string;version:number}
type Report={id:string;used_by:{name:string;title:string|null}[];generation_jobs:string[];bytes:number;files:string[];sizes:Record<string,number>;
  sound:{id:string;label:string;status:string;used_by:{name:string;title:string|null}[];will_delete:boolean}|null}
type Done={id:string;ok:boolean;message:string;freed:number}

const mb=(n:number)=>n>=1024*1024*1024?`${(n/1024/1024/1024).toFixed(2)} GB`:n>=1024*1024?`${(n/1024/1024).toFixed(1)} MB`:`${Math.ceil(n/1024)} KB`
const why=(u:{name:string;title:string|null}[])=>u.slice(0,3).map(x=>x.title??x.name).join(', ')+(u.length>3?` +${u.length-3} more`:'')

export function DeleteClips({clips,cleanup,localUse,onBefore,onDone,onClose}:{clips:DeletableClip[];cleanup:boolean;
  localUse:(id:string)=>string[];onBefore:(ids:string[])=>void;onDone:(removed:string[])=>void;onClose:()=>void}){
  const [mode,setMode]=useState<'library'|'disk'>('library')
  const [withSound,setWithSound]=useState(true)
  const [reports,setReports]=useState<Record<string,Report|string>>({})
  const [checked,setChecked]=useState<Set<string>>(()=>new Set(cleanup?[]:clips.map(c=>c.id)))
  const [busy,setBusy]=useState(false),[done,setDone]=useState<Done[]|null>(null)
  useEffect(()=>{let live=true;const queue=[...clips];const next=async():Promise<void>=>{const c=queue.shift();if(!c||!live)return
    try{const r=await api<Report>(`film/assets/${c.id}/delete`,{mode:'disk',dry_run:true});if(live)setReports(x=>({...x,[c.id]:r}))}
    catch(e){if(live)setReports(x=>({...x,[c.id]:e instanceof Error?e.message:String(e)}))}
    return next()}
    void Promise.all(Array.from({length:Math.min(6,clips.length)},next));return()=>{live=false}},[clips])
  const blockOf=(c:DeletableClip):string|null=>{const local=localUse(c.id);if(local.length)return `Used by unsaved edits in ${local.join(', ')}.`
    const r=reports[c.id];if(r===undefined)return 'Checking…';if(typeof r==='string')return r;return r.used_by.length?`In use by ${why(r.used_by)}.`:null}
  const chosen=clips.filter(c=>checked.has(c.id)&&!blockOf(c))
  // files[0] is the picture; any further files are its production sound.
  const bytes=chosen.reduce((n,c)=>{const r=reports[c.id];if(!r||typeof r==='string')return n;return n+r.files.slice(0,withSound?undefined:1).reduce((m,f)=>m+(r.sizes[f]??0),0)},0)
  const soundCount=chosen.filter(c=>{const r=reports[c.id];return r&&typeof r!=='string'&&r.sound}).length
  const checking=clips.some(c=>reports[c.id]===undefined)
  const order=useMemo(()=>[...clips].sort((a,b)=>a.label.localeCompare(b.label)),[clips])
  async function run(){
    if(!chosen.length||busy)return
    setBusy(true);onBefore(chosen.map(c=>c.id));const out:Done[]=[]
    for(const c of chosen){
      try{const r=await api<{bytes_freed:number;files_left:{path:string;error:string}[];sound:Report['sound']}>(`film/assets/${c.id}/delete`,{mode,include_sound:withSound,expected_version:c.version})
        const left=r.files_left.length?` ${r.files_left.length} file(s) could not be deleted (in use?): ${r.files_left.map(f=>f.path).join(', ')}`:''
        const snd=r.sound?(r.sound.will_delete?' and its production sound':` (its sound was kept${r.sound.used_by.length?`: used by ${why(r.sound.used_by)}`:''})`):''
        out.push({id:c.id,ok:true,freed:r.bytes_freed,message:`${mode==='disk'?'Deleted':'Removed'}${snd}.${mode==='disk'?` Freed ${mb(r.bytes_freed)}.`:''}${left}`})}
      catch(e){out.push({id:c.id,ok:false,freed:0,message:e instanceof Error?e.message:String(e)})}
    }
    setDone(out);setBusy(false);onDone(out.filter(d=>d.ok).map(d=>d.id))
  }
  const label=(id:string)=>clips.find(c=>c.id===id)?.label??id
  return <div className="clip-delete-backdrop" onKeyDown={e=>{e.stopPropagation();if(e.key==='Escape'&&!busy)onClose()}} onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}>
    <div className="clip-delete" role="dialog" aria-modal="true" aria-label={cleanup?'Clean up clips':'Delete clip'}>
      <h2>{cleanup?'Clean up clips':'Delete clip'}</h2>
      {done?<>
        <p>{done.filter(d=>d.ok).length} of {done.length} done{mode==='disk'?` · freed ${mb(done.reduce((n,d)=>n+d.freed,0))}`:''}.</p>
        <ul className="clip-delete-list">{done.map(d=><li key={d.id} data-ok={d.ok}><strong>{label(d.id)}</strong><small>{d.message}</small></li>)}</ul>
        <div className="clip-delete-actions"><button className="ed-primary" autoFocus onClick={onClose}>Close</button></div>
      </>:<>
        <p>{cleanup?'Clips not used by any saved sequence. Tick the ones to remove.':'Take this clip out of the library.'} Clips still on a timeline or in a shot plan can’t be deleted: remove them there first.</p>
        {cleanup?<div className="clip-delete-tools"><button onClick={()=>setChecked(new Set(clips.map(c=>c.id)))}>Tick all</button><button onClick={()=>setChecked(new Set())}>Tick none</button></div>:null}
        <ul className="clip-delete-list">{order.map(c=>{const b=blockOf(c),r=reports[c.id],rep=r&&typeof r!=='string'?r:null
          return <li key={c.id} data-blocked={!!b||undefined}><label><input type="checkbox" checked={checked.has(c.id)&&!b} disabled={!!b||busy} onChange={e=>setChecked(s=>{const n=new Set(s);if(e.target.checked)n.add(c.id);else n.delete(c.id);return n})}/><strong>{c.label}</strong>{rep?<span className="clip-delete-size">{mb(rep.bytes)}</span>:null}</label>
            {b?<small>{b}</small>:rep?.sound?<small>Has production sound “{rep.sound.label}”{rep.sound.used_by.length?` (used by ${why(rep.sound.used_by)}, will be kept)`:''}.</small>:null}</li>})}</ul>
        <fieldset className="clip-delete-mode" disabled={busy}><legend>How</legend>
          <label><input type="radio" name="clip-delete-mode" checked={mode==='library'} onChange={()=>setMode('library')}/>Remove from the editor only <small>The file stays on disk; importing the same file again brings it back as a candidate.</small></label>
          <label><input type="radio" name="clip-delete-mode" checked={mode==='disk'} onChange={()=>setMode('disk')}/>Delete from disk <small>Removes the clip’s file{bytes?` (${mb(bytes)})`:''}. This cannot be undone.</small></label>
          {soundCount?<label><input type="checkbox" checked={withSound} onChange={e=>setWithSound(e.target.checked)}/>Also remove the linked production sound <small>Skipped for any sound still used on a timeline.</small></label>:null}
        </fieldset>
        <p className="clip-delete-note">Generated takes stay in the Queue and can be imported again (the job’s own output is not deleted). A receipt of each removed record is kept.</p>
        <div className="clip-delete-actions"><button onClick={onClose} disabled={busy}>Cancel</button><button className="ed-danger" disabled={busy||checking&&!chosen.length||!chosen.length} onClick={()=>void run()}>{busy?'Working…':`${mode==='disk'?'Delete from disk':'Remove'}: ${chosen.length} clip${chosen.length===1?'':'s'}${mode==='disk'&&bytes?` (${mb(bytes)})`:''}`}</button></div>
      </>}
    </div>
  </div>
}
