import type { TextureSettings } from './editorTypes'
import { DEFAULT_TEXTURE } from './TextureCanvas'

export default function TextureControls({ value, onChange, onApply, busy, dirty }: { value?: TextureSettings; onChange: (value: TextureSettings) => void; onApply: () => void; busy: boolean; dirty: boolean }) {
  const texture = value ?? DEFAULT_TEXTURE
  function update(change: Partial<TextureSettings>) { onChange({ ...texture, ...change }) }
  return <div className="ed-setup">
    <h3>Video texture</h3>
    <p className="ed-help">Moving film grain over the whole picture. Adjust while playing; Apply saves this look for export.</p>
    <fieldset className="ed-texture-controls" disabled={busy}>
    <label className="ed-check"><input type="checkbox" checked={texture.enabled} onChange={e => update({ enabled: e.target.checked })} />Enable video texture</label>
    <label className="ed-field">Strength · {Math.round(texture.strength * 100)}%<input aria-label="Texture strength" type="range" min={0} max={100} step={1} value={Math.round(texture.strength * 100)} onChange={e => update({ strength: Number(e.target.value) / 100 })} /></label>
    <label className="ed-field">Exact strength (%)<input aria-label="Exact texture strength" type="number" min={0} max={100} step={1} value={Math.round(texture.strength * 100)} onChange={e => update({ strength: Math.max(0, Math.min(100, Number(e.target.value))) / 100 })} /></label>
    <label className="ed-field">Grain size · {texture.size}px<input aria-label="Texture grain size" type="range" min={1} max={8} step={1} value={texture.size} onChange={e => update({ size: Number(e.target.value) })} /></label>
    <label className="ed-field">Pattern seed<input aria-label="Texture pattern seed" type="number" min={0} max={2147483647} step={1} value={texture.seed} onChange={e => update({ seed: Math.max(0, Math.min(2147483647, Math.floor(Number(e.target.value)))) })} /></label>
    <div className="ed-action-commands"><button onClick={() => update({ seed: (texture.seed + 1) % 2147483648 })}>New pattern</button><button onClick={() => onChange({ ...DEFAULT_TEXTURE })}>Reset</button></div>
    <p className="ed-help">Coverage: full sequence. The same pattern seed and episode frame reproduce the grain across cuts and holds.</p>
    <button className="ed-primary" disabled={busy || !dirty} onClick={onApply}>Apply texture settings</button>
    </fieldset>
    {dirty ? <p className="ed-help">Live preview · changes are not saved yet.</p> : null}
  </div>
}
