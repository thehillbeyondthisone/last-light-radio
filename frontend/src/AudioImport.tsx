import { useEffect, useRef, useState } from 'react'
import { api, encodeFile } from './api'
import type { AudioAsset } from './editorTypes'

type Capability = { begin_url?: string; mode?:string; max_bytes: number; max_duration_seconds: number; content_type:string }
export default function AudioImport({ disabled, provenance, onImported, onBusy }: {disabled:boolean;provenance:string;onBusy:(busy:boolean)=>void;onImported:(asset:AudioAsset)=>Promise<void>}) {
 const [cap,setCap]=useState<Capability|null>(null),[stage,setStage]=useState(''),[percent,setPercent]=useState<number|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const xhr=useRef<XMLHttpRequest|null>(null),lock=useRef(false),mounted=useRef(true)
 useEffect(()=>{mounted.current=true;void api<{upload?:Capability}>('audio').then(r=>{if(mounted.current)setCap(r.upload&&(r.upload.mode==='binary'||r.upload.content_type==='application/octet-stream')?r.upload:null)}).catch(()=>{});return()=>{mounted.current=false;xhr.current?.abort()}},[])
 useEffect(()=>{if(!busy)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[busy])
 async function upload(file:File){
  if(disabled||lock.current)return
  lock.current=true;setBusy(true);onBusy(true);setError('');setPercent(null);setStage('Preparing import')
  try{
   const metadata=provenance.trim()?JSON.parse(provenance):{}
   if(!metadata||Array.isArray(metadata)||typeof metadata!=='object')throw new Error('Provenance must be a JSON object.')
   const max=cap?.max_bytes??20*1024*1024
   if(!/\.wav$/i.test(file.name)||file.size<1||file.size>max)throw new Error(`Choose a WAV no larger than ${Math.floor(max/1024/1024)} MiB.`)
   let asset:AudioAsset
   if(cap){
    const ticket=await api<{upload_url:string;max_bytes:number}>('audio/uploads',{filename:file.name,label:file.name.replace(/\.wav$/i,''),provenance:metadata,bytes:file.size})
    if(!mounted.current)return
    if(file.size>ticket.max_bytes)throw new Error('The server upload limit changed. No file was sent.')
    const url=new URL(ticket.upload_url,location.origin)
    if(url.origin!==location.origin||!url.pathname.startsWith('/api/audio/uploads/'))throw new Error('Unexpected upload destination; no file was sent.')
    setStage('Uploading original WAV')
    asset=await new Promise<AudioAsset>((resolve,reject)=>{
     const req=new XMLHttpRequest();xhr.current=req;req.open('POST',url.href);req.setRequestHeader('Content-Type','application/octet-stream');req.setRequestHeader('X-LLR-Client','studio')
     req.upload.onprogress=e=>{if(mounted.current&&e.lengthComputable)setPercent(Math.floor(e.loaded/e.total*100))}
     req.upload.onload=()=>{if(mounted.current){setPercent(null);setStage('Uploaded. Decoding and verifying audio; no progress estimate available.')}}
     req.onload=()=>{try{const result=JSON.parse(req.responseText);if(req.status<200||req.status>=300)throw new Error(result.error?.message??`Import failed (${req.status})`);resolve(result)}catch(e){reject(e)}}
     req.onerror=()=>reject(new Error('Connection interrupted. The import may have completed. Refresh the audio library before retrying; the original-file hash prevents duplicate assets.'))
     req.onabort=()=>reject(new Error('Stopped waiting for upload. If all bytes arrived, processing may still complete. Refresh the audio library before retrying.'))
     req.send(file)
    })
   }else{
    setStage('Importing WAV through the compatible small-file route')
    asset=await api<AudioAsset>('audio/import',{filename:file.name,label:file.name.replace(/\.wav$/i,''),audio_base64:await encodeFile(file),provenance:metadata})
   }
   if(mounted.current){await onImported(asset);setStage('Import verified. Audition and review this source before placing it.')}
  }catch(e){if(mounted.current){setError(e instanceof Error?e.message:String(e));setStage('')}}
  finally{xhr.current=null;lock.current=false;if(mounted.current){setBusy(false);onBusy(false);setPercent(null)}}
 }
 return <div><label className="ed-field">Import WAV<input aria-label="Import audio WAV" type="file" accept=".wav,audio/wav" disabled={disabled||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void upload(file)}}/></label><p className="ed-help">{cap?`Original WAV up to ${Math.floor(cap.max_bytes/1024/1024)} MiB / ${cap.max_duration_seconds}s. Sent directly without a base64 copy.`:'Compatible WAV import up to 20 MiB. Larger-file support is not advertised by this server.'}</p>{stage?<p role="status">{stage}{percent!==null?` (${percent}% bytes sent)`:''}</p>:null}{percent!==null?<progress value={percent} max={100} aria-label="WAV upload bytes"/>:null}{busy&&cap?<button onClick={()=>xhr.current?.abort()} disabled={!xhr.current}>Stop waiting</button>:null}{error?<p role="alert">{error}</p>:null}</div>
}
