import {useState} from 'react'

/** Generate › Selected take: the clip's recorded prompt, editable, handed to the New generation form.
 *  Nothing is generated here; the form still runs its own worker check before anything is queued. */
export function ClipPrompt({prompt,onUse}:{prompt?:string;onUse:(text:string)=>void}){
  const [text,setText]=useState(prompt??'')
  return <div className="gen-clip-prompt" onKeyDown={e=>e.stopPropagation()}>
    <label>Clip prompt<textarea aria-label="Clip prompt" value={text} rows={5} onChange={e=>setText(e.target.value)} placeholder={prompt?undefined:'No prompt was recorded with this clip. Write one to generate a new take.'}/></label>
    {!prompt?<p className="gen-clip-prompt-note">No prompt recorded with this clip.</p>:null}
    <div className="gen-clip-prompt-row"><button className="ed-primary" disabled={!text.trim()} onClick={()=>onUse(text.trim())}>Edit in New generation</button>{prompt&&text!==prompt?<button onClick={()=>setText(prompt)}>Reset to recorded prompt</button>:null}<small>Only the prompt carries over. Seed, reference frames and placement are set in the New generation form.</small></div>
  </div>
}
