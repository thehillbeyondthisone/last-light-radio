/** Isolated UI fixture: synthetic sources only, no API requests or production library writes. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import FilmBin, { sourceKey, useUserBins } from '../src/FilmBin'
import type { BinItem } from '../src/FilmBin'
import { emptyBrowserSelection } from '../src/browserSelection'
import '../src/fcpFilm.css'

const items: BinItem[] = [
  { id: 'a', kind: 'video', label: 'Alpha', status: 'approved', seconds: 2 },
  { id: 'b', kind: 'video', label: 'Bravo', status: 'candidate', seconds: 3 },
  { id: 'c', kind: 'video', label: 'Charlie', status: 'approved', seconds: 4 },
  { id: 'a', kind: 'audio', label: 'Delta audio', status: 'approved', seconds: 5 },
  { id: 'e', kind: 'still', label: 'Echo still', status: 'reference', seconds: null },
]
function Fixture() {
  const [selection, setSelection] = useState(emptyBrowserSelection)
  const [openId, setOpenId] = useState('')
  const [menu, setMenu] = useState('')
  const bins = useUserBins()
  return <main className="fcp-film" style={{ width: 480 }}>
    <h1>Browser selection fixture</h1>
    <FilmBin items={items} usedCount={new Map()} inSequence={new Set()} openKey={openId} selection={selection} onSelection={setSelection} busy={false}
      onOpen={i => setOpenId(sourceKey(i.kind, i.id))} onReject={() => {}} onMenu={(_i, _x, _y, keys) => setMenu(keys.join(', '))} />
    <p>Opened: {openId || 'none'}</p><p>Menu selection: {menu || 'none'}</p>
    <pre aria-label="Bin membership">{JSON.stringify(bins.member)}</pre>
  </main>
}
createRoot(document.getElementById('root')!).render(<Fixture />)
