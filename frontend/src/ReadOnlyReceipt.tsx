import type {ReactNode} from 'react'
export function ReadOnlyReceipt({provenance,missing,hidePrompt}:{provenance?:Record<string,unknown>;missing:ReactNode;hidePrompt?:boolean}){
 const record=provenance?.generation_metadata??provenance?.generation
 if(!record||typeof record!=='object'||Array.isArray(record))return missing
 const r=record as Record<string,unknown>
 const prompt=typeof r.brief==='string'?r.brief:typeof r.prompt==='string'?r.prompt:undefined
 const seed=typeof r.seed==='number'&&Number.isSafeInteger(r.seed)?r.seed:undefined
 const reference=typeof r.reference==='string'?r.reference:undefined
 if(!prompt&&seed===undefined&&!reference)return missing
 return <section><p>Imported generation record. These settings were recorded with the source, but no replayable editor job was found.</p><dl><dt>Seed</dt><dd>{seed??'Not recorded'}</dd><dt>Reference</dt><dd>{reference??'Not recorded in this record'}</dd></dl>{prompt&&!hidePrompt?<><p>Recorded prompt</p><blockquote style={{whiteSpace:'pre-wrap'}}>{prompt}</blockquote></>:null}</section>
}
