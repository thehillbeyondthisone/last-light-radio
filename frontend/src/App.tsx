import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import Icon from './Icon'
import SceneView, { ImportDialog } from './SceneView'
import GenerateView from './GenerateView'
import ReviewView from './ReviewView'
import WorkerView from './WorkerView'
import MotionGuide from './MotionGuide'
import PilotView from './PilotView'
import EditorView from './EditorView'
import FilmEditor from './FilmEditor'
import type { MotionProfile, Scene, StudioState, View } from './types'

const navigation: { view: View; icon: 'scene' | 'spark' | 'review'; title: string; detail: string }[] = [
  { view: 'film', icon: 'scene', title: 'Film editor', detail: 'Projects, sequences and shots' },
  { view: 'editor', icon: 'scene', title: 'Scene animation', detail: 'Compose a single animated scene' },
  { view: 'scenes', icon: 'scene', title: 'Scenes', detail: 'Choose a scene and add motion' },
  { view: 'review', icon: 'review', title: 'Review', detail: 'Watch and keep takes' },
  { view: 'pilot', icon: 'scene', title: 'Episode', detail: 'Arrange approved motions' },
]
const titles: Record<View, string> = { film: 'Film editor', editor: 'Scene animation', scenes: 'Scene studio', setup: 'Scene setup', generate: 'Motion studio', review: 'Review room', pilot: 'Pilot builder', worker: 'Worker connection' }

export default function App() {
  const [data, setData] = useState<StudioState | null>(null)
  const [view, setView] = useState<View>('film')
  const [sceneId, setSceneId] = useState(() => {
    try { return localStorage.getItem('llr.scene.v1') ?? '' } catch { return '' }
  })
  const [candidateId, setCandidateId] = useState('')
  const [recipeId, setRecipeId] = useState('')
  const [editing, setEditing] = useState<MotionProfile | undefined>()
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'auto' }) }, [view])
  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await api<StudioState>('state', undefined, signal)
      setData(result)
      setError('')
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setError(error instanceof Error ? error.message : 'Could not reach the local studio.')
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [refresh])
  const active = (data?.jobs.some((job) => ['pending', 'submitting', 'queued', 'running', 'unknown'].includes(job.status)) ?? false) || ([...(data?.pilots ?? []), ...(data?.sequences ?? [])].some((pilot) => ['queued', 'exporting'].includes(pilot.status)))
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(controller.signal) }, 4000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [active, refresh])
  useEffect(() => {
    if (!flash) return
    const timer = window.setTimeout(() => setFlash(''), 6500)
    return () => window.clearTimeout(timer)
  }, [flash])
  const primarySceneId = data?.pilot_catalog?.slice().sort((a, b) => b.approved_count - a.approved_count)[0]?.scene_id
  const scene = data?.scenes.find((item) => item.id === sceneId) ?? data?.scenes.find((item) => item.id === primarySceneId) ?? data?.scenes[0]
  useEffect(() => {
    if (scene) { try { localStorage.setItem('llr.scene.v1', scene.id) } catch { /* Storage can be disabled. */ } }
  }, [scene?.id])
  const pending = data?.candidates.filter((item) => item.status === 'candidate').length ?? 0
  function openReview(id: string) { setCandidateId(id); setView('review') }
  async function imported(next: Scene) {
    await refresh(); setSceneId(next.id); setEditing(undefined); setView('editor'); setImporting(false)
    setFlash('Scene imported. Your original image is preserved.')
  }
  function setup(profile?: MotionProfile) { setEditing(profile); setView('setup') }
  function saved(profile: MotionProfile, generating = false) { setRecipeId(profile.id); setSceneId(profile.scene_id); setView('generate'); setFlash(generating ? 'Your first take is underway. It will appear here when ready.' : 'Motion saved. Make a take whenever you’re ready.') }
  if (view === 'film' && data) return <FilmEditor data={data} onSceneAnimation={() => setView('editor')} onGenerate={() => setView('generate')} />
  if (view === 'editor') return <>
    {data ? <EditorView key={scene?.id ?? 'empty'} data={data} scene={scene} onScene={setSceneId} refresh={refresh} notify={setFlash} onImport={() => setImporting(true)} onWorker={() => setView('worker')} onLegacy={() => setView('film')} /> : <div className="empty-state"><h1>Opening the editor</h1><p>Loading your scenes and action library.</p></div>}
    {error ? <div className="error-banner" role="alert">{error}<button onClick={() => void refresh()}>Try again</button></div> : null}
    {flash ? <div className="toast" role="status">{flash}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setFlash('')}><Icon name="close" size={16} /></button></div> : null}
    {importing ? <ImportDialog onClose={() => setImporting(false)} onImported={imported} /> : null}
  </>
  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <aside className="sidebar">
      <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setView('scenes') }} aria-label="Last Light Radio home">
        <span className="brand-symbol"><Icon name="radio" size={25} /></span>
        <span>LAST LIGHT<span className="brand-small">R A D I O</span></span>
      </a>
      <div className="workspace-label"><span className="tiny-light" /> CREATOR WORKSPACE</div>
      <nav aria-label="Main navigation">{navigation.map((item) => <button key={item.view} className={`nav-item ${view === item.view || (item.view === 'scenes' && ['setup', 'generate'].includes(view)) ? 'active' : ''}`} onClick={() => { if (item.view === 'review') setCandidateId(''); setView(item.view) }} aria-current={view === item.view ? 'page' : undefined}>
        <Icon name={item.icon} /><span>{item.title}<small>{item.detail}</small></span>{item.view === 'review' && pending > 0 ? <span className="nav-count">{pending}</span> : null}
      </button>)}</nav>
      <div className="sidebar-section"><span>YOUR SCENES</span><button className="icon-button" title="Import a scene" aria-label="Import a scene" onClick={() => setImporting(true)}><Icon name="plus" size={16} /></button></div>
      <div className="scene-navigation">{data?.scenes.map((item) => <button key={item.id} className={`scene-link ${scene?.id === item.id ? 'selected' : ''}`} onClick={() => { setSceneId(item.id); setView('scenes') }}>
        <img src={item.thumbnail_url} alt="" /><span>{item.title}<small>{item.fixture ? 'Technical test scene' : 'Imported scene'}</small></span>
      </button>)}</div>
      <div className="sidebar-bottom"><p>Music for places<br /><em>that are still awake.</em></p><button className={`connection-link ${view === 'worker' ? 'selected' : ''}`} onClick={() => setView('worker')}><Icon name="settings" /><span>ComfyUI worker</span><span className={`status-dot ${data?.worker.connected ? 'online' : ''}`} /></button><small className="local-label">LOCAL STUDIO <span>v0.2</span></small></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Workspace <Icon name="chevron" size={13} /><strong>{titles[view]}</strong></div><div className="topbar-actions"><button className="worker-pill" onClick={() => setView('worker')}><span className={`status-dot ${data?.worker.connected ? 'online' : ''}`} />H3 worker · {data?.worker.connected ? 'connected' : 'not checked'}</button><button className="button dark compact" onClick={() => setImporting(true)}><Icon name="plus" size={16} />Import scene</button></div></header>
      <main id="workspace" tabIndex={-1}>
        {error ? <div className="error-banner" role="alert">{error}<button onClick={() => void refresh()}>Try again</button></div> : null}
        {!data ? <div className="empty-state"><span className="loading-ring" /><h1>Opening your studio</h1><p>Loading scenes and your motion library.</p></div> : <>
          {view === 'scenes' ? <SceneView scene={scene} candidates={data.candidates} profiles={data.motion_profiles ?? []} onSetup={setup} onImport={() => setImporting(true)} onGenerate={(id) => { setRecipeId(id ?? ''); setView('generate') }} onReview={openReview} /> : null}
          {view === 'setup' ? <MotionGuide data={data} scene={scene} editing={editing} onScene={setSceneId} onImport={() => setImporting(true)} onCancel={() => setView('scenes')} refresh={refresh} onSaved={saved} /> : null}
          {view === 'generate' ? <GenerateView data={data} scene={scene} preferredProfileId={recipeId} onSetup={() => setup()} onScene={setSceneId} refresh={refresh} notify={setFlash} onReview={openReview} onWorker={() => setView('worker')} /> : null}
          {view === 'review' ? <ReviewView data={data} preferredId={candidateId} refresh={refresh} notify={setFlash} onBack={() => {
            const candidate = data.candidates.find((item) => item.id === candidateId)
            if (candidate) { setSceneId(candidate.scene_id); setRecipeId(candidate.metadata.motion?.profile_id ?? '') }
            setView('generate')
          }} /> : null}
          {view === 'pilot' ? <PilotView data={data} refresh={refresh} notify={setFlash} /> : null}
          {view === 'worker' ? <WorkerView worker={data.worker} imports={data.imports} refresh={refresh} notify={setFlash} /> : null}
        </>}
      </main>
    </div>
    {flash ? <div className="toast" role="status"><Icon name="check" />{flash}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setFlash('')}><Icon name="close" size={16} /></button></div> : null}
    {importing ? <ImportDialog onClose={() => setImporting(false)} onImported={imported} /> : null}
  </div>
}

