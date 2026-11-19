import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import Icon from './Icon'
import type { StudioState, Worker } from './types'

export default function WorkerView({ worker, imports, refresh, notify }: { worker: Worker; imports: StudioState['imports']; refresh: () => Promise<void>; notify: (text: string) => void }) {
  const [url, setUrl] = useState(worker.url)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [library, setLibrary] = useState('')
  const [importing, setImporting] = useState(false)
  async function connect(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await api<Worker>('worker', { url }); await refresh()
      if (!result.connected || !result.workflow_valid) setError(result.errors?.map((error) => error.message).join(' · ') || 'The worker is not ready for the small-test workflow.')
      else if (result.production_workflow_valid === false) notify('ComfyUI connected. Recovered actor motion needs attention; see the workflow details.')
      else if (result.production_workflow_valid === true) notify('ComfyUI connected. Both H3 pipelines pass compatibility checks for the configured models.')
      else notify('ComfyUI connected. The small-test workflow is compatible; actor motion has not been checked.')
    } catch (error) { setError(error instanceof Error ? error.message : 'Connection failed.') }
    finally { setBusy(false) }
  }
  async function importLibrary() {
    setImporting(true); setError('')
    try { const result = await api<{ message: string }>('library/import', { path: library }); await refresh(); notify(result.message) }
    catch (error) { setError(error instanceof Error ? error.message : 'Library import failed.') }
    finally { setImporting(false) }
  }
  return <section className="page settings-page">
    <div className="page-heading"><div><p className="eyebrow">YOUR LOCAL WORKER</p><h1>Connected, close to home.</h1><p>Generate with your own ComfyUI setup. Keep your media local.</p></div></div>
    <form className="panel connection-form" onSubmit={(event) => void connect(event)}>
      <div className="panel-title"><h2>ComfyUI connection</h2><span className={`badge ${worker.connected ? 'approved' : 'neutral'}`}>{worker.connected ? 'Connected' : 'Not checked'}</span></div>
      <label className="field">Worker address<input type="url" required value={url} onChange={(event) => setUrl(event.target.value)} placeholder="http://192.168.1.168:8188" /></label><p className="field-help">Use the full address of the machine running ComfyUI.</p><button className="button dark" disabled={busy}><Icon name="refresh" size={16} />{busy ? 'Checking worker…' : 'Test & save connection'}</button>
      {worker.devices?.length ? <div className="worker-details">{worker.devices.map((device) => <div key={device.name}><strong>{device.name.replace('cuda:0 ', '').replace(' : cudaMallocAsync', '')}</strong><span>{(device.vram_total / 1024 ** 3).toFixed(1)} GB reported VRAM</span></div>)}<p>{worker.node_count} installed node classes</p></div> : null}
      <div className="worker-details">
        <div className="detail-pair"><span>Small full-scene smoke test</span><strong>{worker.workflow_valid === undefined ? 'Not checked' : worker.workflow_valid ? 'Compatible' : 'Needs attention'}</strong></div>
        {worker.errors?.length ? <ul className="form-error" aria-label="Small-test workflow errors">{worker.errors.map((item, index) => <li key={`${index}-${item.message}`}>{item.message}</li>)}</ul> : null}
        <div className="detail-pair"><span>Recovered actor motion</span><strong>{worker.production_workflow_valid === undefined ? 'Not checked' : worker.production_workflow_valid ? 'Compatible' : 'Needs attention'}</strong></div>
        <p className="field-help">Actor compatibility uses the configured production VAE. The selected video VAE is recorded with each generated take.</p>
        {worker.production_errors?.length ? <ul className="form-error" aria-label="Recovered actor workflow errors">{worker.production_errors.map((item, index) => <li key={`${index}-${item.message}`}>{item.message}</li>)}</ul> : null}
      </div>
      {worker.checked_at ? <p className="field-help">Last checked {new Date(worker.checked_at).toLocaleString()}</p> : null}
    </form>
    <div className="panel library-import"><div className="panel-title"><h2>Import an earlier library</h2><Icon name="scene" /></div><p className="muted">Bring scenes, clips and recorded review decisions into this separate working store. The original library is opened read-only.</p><label className="field">Existing media folder<input value={library} onChange={(event) => setLibrary(event.target.value)} placeholder="D:\LastLightRadioMedia" /></label><button className="button light" disabled={importing || !library.trim()} onClick={() => void importLibrary()}><Icon name="upload" size={16} />{importing ? 'Importing library…' : 'Import existing library'}</button>{imports.map((item) => <div className="worker-details" key={item.source}><strong>{item.source}</strong><span>{item.scene_count} scenes · {item.candidate_count} clips · {item.sequence_count} archived exports</span><p>Originals preserved. Prior decisions are labeled as imported history.</p></div>)}</div>
    {error ? <div className="form-error" role="alert">{error}</div> : null}<div className="settings-footnote"><Icon name="lock" /><p>The studio checks node compatibility before a render. It keeps workflow and image snapshots with every job. Checking this connection never submits GPU work.</p></div>
  </section>
}
