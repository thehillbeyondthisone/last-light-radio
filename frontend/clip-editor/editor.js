const $ = (id) => document.getElementById(id)
const video = $('viewer')
const frame = $('frame')
const prompt = $('prompt')
const length = $('length')
const statuses = {
  pending: 'Waiting to submit', submitting: 'Sending to ComfyUI', queued: 'Queued at ComfyUI',
  running: 'Generating', unknown: 'Waiting for worker status', failed: 'Generation failed',
  success: 'Importing clip', submission_unknown: 'Submission status unknown',
}

function restore(key) {
  try { return localStorage.getItem('llr.clipEditor.' + key) || '' } catch { return '' }
}

function remember(key, value) {
  try { localStorage.setItem('llr.clipEditor.' + key, value) } catch { /* Draft storage is optional. */ }
}

let state
let imageId = restore('image')
let wantedJob = restore('job')
let activeClip
let activeShot
let playback
let busy = false
let online = false
let refreshVersion = 0
let attempt
let warnedCheck
const signatures = new Map()
try { attempt = JSON.parse(restore('attempt')) || undefined } catch { /* A new request can still be made. */ }
prompt.value = restore('prompt')

async function api(path = '', payload) {
  const response = await fetch('/api/clips' + path, payload === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-LLR-Client': 'studio' },
    body: JSON.stringify(payload),
  })
  const result = await response.json()
  if (!response.ok) {
    const error = new Error(result.error?.message || `Request failed (${response.status})`)
    error.status = response.status
    throw error
  }
  return result
}

function show(id, message) {
  $(id).textContent = message || ''
  $(id).hidden = !message
}

function onceChanged(key, data, draw) {
  const signature = JSON.stringify(data)
  if (signatures.get(key) === signature) return
  signatures.set(key, signature)
  draw()
}

const clipById = (id) => state?.clips.find((clip) => clip.id === id)
const imageById = (id) => state?.images.find((image) => image.id === id)
const fps = () => state.recipe.fps
const seconds = (frames) => `${(frames / fps()).toFixed(2).replace(/\.?0+$/, '')} s`
const randomId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) => n.toString(16).padStart(2, '0')).join('')

function updateControls() {
  const hasClip = activeClip && !playback
  $('generate-controls').disabled = !state || busy
  $('draft').disabled = !imageById(imageId) || !prompt.value.trim() || !state?.local_ai_configured
  $('generate').disabled = !imageById(imageId) || !prompt.value.trim() || !state?.worker_configured
  $('generate').textContent = warnedCheck ? 'Generate anyway' : 'Generate clip'
  $('clip-tools').hidden = !hasClip
  $('use-frame').disabled = busy || video.readyState < 1
  $('add').disabled = busy
  frame.disabled = video.readyState < 1
  $('frame-prev').disabled = frame.disabled || Number(frame.value) === 0
  $('frame-next').disabled = frame.disabled || Number(frame.value) >= Number(frame.max)
  if (!state) return
  const index = state.sequence.shots.findIndex((shot) => shot.id === activeShot)
  $('move-left').disabled = busy || index <= 0
  $('move-right').disabled = busy || index < 0 || index >= state.sequence.shots.length - 1
  $('remove').disabled = busy || index < 0
  $('edit-tools').hidden = index < 0
  const hasShots = state.sequence.shots.length > 0
  $('play-sequence').disabled = !hasShots || busy
  $('export').disabled = !hasShots || busy || ['queued', 'exporting'].includes(state.sequence.export.status)
}

function showLength() {
  const selected = Number(length.value)
  $('length-readout').value = seconds(selected)
  show('length-note', state.recipe.proven_frames.includes(selected) ? '' : 'This length still needs a live worker check.')
}

function chooseImage(id) {
  imageId = id
  remember('image', id)
  const image = imageById(id)
  const preview = $('source-image')
  if (image && preview.getAttribute('src') !== image.media_url) preview.src = image.media_url
  preview.alt = image?.label || ''
  preview.hidden = !image
  $('source-empty').hidden = !!image
  $('image-picker').value = id
  updateControls()
}

function tile(clip, caption, selected, open) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'tile'
  button.setAttribute('aria-pressed', String(selected))
  button.addEventListener('click', open)
  const image = imageById(clip.image_id)
  const thumb = document.createElement(image ? 'img' : 'span')
  if (image) {
    thumb.src = image.media_url
    thumb.alt = ''
    thumb.loading = 'lazy'
  } else {
    thumb.className = 'thumb-empty'
  }
  const title = document.createElement('strong')
  title.textContent = clip.label
  const detail = document.createElement('small')
  detail.textContent = caption
  button.append(thumb, title, detail)
  return button
}

function drawClips() {
  const clips = state.clips
  onceChanged('clips', [clips, activeClip?.id, !!playback], () => {
    $('clip-count').textContent = clips.length ? String(clips.length) : ''
    $('clips-empty').hidden = !!clips.length
    $('clips').replaceChildren(...clips.map((clip) =>
      tile(clip, seconds(clip.frames), clip.id === activeClip?.id && !playback, () => openClip(clip))))
  })
  const shots = state.sequence.shots
  onceChanged('timeline', [shots, activeShot, playback?.index], () => {
    $('timeline-empty').hidden = !!shots.length
    $('timeline').replaceChildren(...shots.map((shot, index) => {
      const item = document.createElement('li')
      const clip = clipById(shot.asset_id)
      if (clip) {
        item.append(tile(clip, `${index + 1}  ·  ${seconds(shot.duration_frames)}`, shot.id === activeShot,
          () => openClip(clip, shot.id)))
      }
      return item
    }))
    $('sequence-length').textContent = shots.length ? `${shots.length} ${shots.length === 1 ? 'clip' : 'clips'} · ${seconds(state.sequence.duration_frames)}` : ''
  })
}

function drawJobs() {
  const jobs = state.jobs.filter((job) => !job.video_asset_id)
  onceChanged('jobs', [jobs, busy], () => {
    $('jobs').replaceChildren(...jobs.map((job) => {
      const row = document.createElement('div')
      row.className = 'job'
      const label = document.createElement('div')
      const name = document.createElement('strong')
      const status = document.createElement('small')
      name.textContent = job.label
      status.textContent = [job.import_error ? 'Import failed' : statuses[job.status] || job.status,
        job.import_error || job.error?.message].filter(Boolean).join(' · ')
      label.append(name, status)
      row.append(label)
      if (job.import_error || (job.can_resume && job.status === 'failed')) {
        const retry = document.createElement('button')
        retry.textContent = job.import_error ? 'Retry import' : 'Check again'
        retry.disabled = busy
        retry.addEventListener('click', () => act(async () => {
          await api(`/jobs/${job.id}/${job.import_error ? 'import' : 'resume'}`, {})
          await refresh()
        }))
        row.append(retry)
      }
      return row
    }))
  })
}

function render() {
  $('connection').textContent = !online ? 'Connection lost' : state.worker_configured ? 'Editor connected' : 'ComfyUI setup needed'
  $('connection').dataset.online = String(online)
  onceChanged('local-ai', state.local_ai_configured ?? false, () => {
    show('draft-message', state.local_ai_configured ? '' : 'Set up local-ai.json in the Clip Editor library to draft with Local AI.')
  })
  const recipe = state.recipe
  onceChanged('recipe', recipe, () => {
    length.min = recipe.min_frames
    length.max = recipe.max_frames
    length.step = recipe.frame_step
    length.value = Number(restore('length')) || recipe.frames
    $('min-length').textContent = seconds(recipe.min_frames)
    $('max-length').textContent = seconds(recipe.max_frames)
    showLength()
  })
  onceChanged('images', state.images, () => {
    $('image-picker').replaceChildren(...state.images.map((image) => new Option(image.label, image.id)))
    $('image-picker').hidden = !state.images.length
  })
  chooseImage(imageById(imageId)?.id || state.images[0]?.id || '')
  const job = state.jobs.find((item) => item.id === wantedJob)
  const finished = clipById(job?.video_asset_id)
  if (finished) {
    wantedJob = ''
    remember('job', '')
    if (!playback) openClip(finished)
    show('generation-message', 'Clip ready in Clips.')
  } else if (!activeClip && !playback && state.clips.length) {
    openClip(state.clips[0])
  }
  if (activeShot && !state.sequence.shots.some((shot) => shot.id === activeShot)) activeShot = undefined
  drawClips()
  drawJobs()
  const exported = state.sequence.export
  $('download').hidden = exported.status !== 'complete'
  if (exported.media_url) $('download').href = exported.media_url
  show('export-status', exported.error || ({
    queued: 'Export queued…', exporting: 'Exporting sequence…', complete: 'MP4 ready to download.',
  })[exported.status])
  updateControls()
}

async function refresh() {
  const request = ++refreshVersion
  const next = await api()
  if (request !== refreshVersion) return
  state = next
  online = true
  render()
}

async function act(operation) {
  if (busy) return
  busy = true
  // Ignore any poll that started before a write or preflight.
  refreshVersion++
  show('error', '')
  updateControls()
  try {
    await operation()
  } catch (error) {
    show('error', error.message)
    if (error.status === 409) await refresh().catch(() => {})
  } finally {
    busy = false
    if (state) drawJobs()
    updateControls()
  }
}

function loadClip(clip) {
  activeClip = clip
  video.pause()
  video.hidden = false
  $('viewer-empty').hidden = true
  video.poster = imageById(clip.image_id)?.media_url || ''
  video.src = clip.media_url
  frame.max = clip.frames - 1
  frame.value = 0
  readFrame()
  show('viewer-message', '')
}

function openClip(clip, shotId) {
  playback = undefined
  activeShot = shotId
  loadClip(clip)
  $('viewer-label').textContent = clip.label
  drawClips()
  updateControls()
}

function readFrame() {
  const index = Number(frame.value)
  $('frame-readout').value = `${seconds(index)} · frame ${index + 1} of ${activeClip.frames}`
  updateControls()
}

function seekFrame(index) {
  if (!activeClip || video.readyState < 1) return
  video.pause()
  frame.value = Math.max(0, Math.min(activeClip.frames - 1, index))
  video.currentTime = (Number(frame.value) + .1) / fps()
  readFrame()
}

function playPlacement() {
  const shot = playback.shots[playback.index]
  const clip = clipById(shot.asset_id)
  if (!clip) {
    show('viewer-message', 'A clip in this sequence is unavailable.')
    playback = undefined
    updateControls()
    return
  }
  activeShot = shot.id
  loadClip(clip)
  $('viewer-label').textContent = `Sequence · ${playback.index + 1} of ${playback.shots.length}`
  drawClips()
  updateControls()
  const playing = playback
  video.play().catch((error) => {
    if (playing === playback && error.name !== 'AbortError') show('viewer-message', 'Tap Play in the viewer to continue.')
  })
}

async function saveShots(shots) {
  const next = await api('/sequence', { shots, expected_revision: state.sequence.revision })
  state = next
  render()
}

function editShot(offset) {
  return act(async () => {
    const shots = [...state.sequence.shots]
    const index = shots.findIndex((shot) => shot.id === activeShot)
    if (index < 0) return
    const [shot] = shots.splice(index, 1)
    if (offset) shots.splice(index + offset, 0, shot)
    await saveShots(shots)
  })
}

function upload() { $('upload').click() }

async function convertHeif(file) {
  const url = URL.createObjectURL(file)
  try {
    const photo = new Image()
    photo.src = url
    await photo.decode()
    const scale = Math.min(1, 2048 / Math.max(photo.naturalWidth, photo.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(photo.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(photo.naturalHeight * scale))
    canvas.getContext('2d').drawImage(photo, 0, 0, canvas.width, canvas.height)
    const jpeg = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .94))
    if (!jpeg) throw new Error('JPEG encoding failed')
    return jpeg
  } catch {
    throw new Error('This browser could not open the HEIC photo. Export it as JPEG or PNG and upload it again.')
  } finally {
    URL.revokeObjectURL(url)
  }
}

$('upload-button').addEventListener('click', upload)
$('source-empty').addEventListener('click', upload)
$('upload').addEventListener('change', (event) => {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  void act(async () => {
    if (file.size > 20 * 1024 * 1024) throw new Error('Choose an image up to 20 MiB.')
    const heif = /\.(heic|heif)$/i.test(file.name) || /^image\/hei[cf]$/i.test(file.type)
    const photo = heif ? await convertHeif(file) : file
    const image_base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result).split(',')[1])
      reader.onerror = () => reject(new Error('Could not read the selected image.'))
      reader.readAsDataURL(photo)
    })
    const filename = heif ? file.name.replace(/\.(heic|heif)$/i, '') + '.jpg' : file.name
    const image = await api('/images', { filename, label: file.name, image_base64, converted_from_heif: heif })
    imageId = image.id
    await refresh()
  })
})
$('image-picker').addEventListener('change', (event) => { warnedCheck = undefined; chooseImage(event.target.value) })
prompt.addEventListener('input', () => {
  remember('prompt', prompt.value)
  warnedCheck = undefined
  updateControls()
})
length.addEventListener('input', () => {
  remember('length', length.value)
  warnedCheck = undefined
  showLength()
  updateControls()
})
$('draft').addEventListener('click', () => {
  void act(async () => {
    show('draft-message', 'Drafting with Local AI…')
    try {
      const draft = await api('/draft', {
        first_frame_id: imageId, direction: prompt.value.trim(), length_frames: Number(length.value),
      })
      prompt.value = draft.brief
      length.value = draft.length_frames
      prompt.dispatchEvent(new Event('input'))
      length.dispatchEvent(new Event('input'))
      show('draft-message', 'Draft ready. Review the prompt and length before generating.')
    } catch (error) {
      show('draft-message', error.message)
    }
  })
})
$('generate-form').addEventListener('submit', (event) => {
  event.preventDefault()
  void act(async () => {
    const inputs = { first_frame_id: imageId, brief: prompt.value.trim(), length_frames: Number(length.value) }
    const key = JSON.stringify(inputs)
    if (attempt?.key !== key) {
      attempt = { key, id: randomId(), body: { ...inputs, seed: crypto.getRandomValues(new Uint32Array(1))[0] >>> 1 } }
      remember('attempt', JSON.stringify(attempt))
    }
    const check = attempt.check && Date.parse(attempt.check.expires_at) > Date.now()
      ? attempt.check
      : await api('/preflight', attempt.body)
    if (!check.ready) throw new Error(check.errors.map((error) => error.message).join(' · ') || 'The ComfyUI check failed.')
    attempt.check = check
    if (check.warnings.length && warnedCheck !== check.id) {
      warnedCheck = check.id
      show('generation-message', check.warnings.map((warning) => warning.message).join(' · '))
      return
    }
    const job = await api('/generate', { ...attempt.body, preflight_id: check.id, request_id: attempt.id })
    wantedJob = job.id
    remember('job', wantedJob)
    warnedCheck = undefined
    attempt = undefined
    remember('attempt', '')
    show('generation-message', 'Clip requested. Follow its progress in Clips.')
    await refresh()
  })
})
frame.addEventListener('input', () => seekFrame(Number(frame.value)))
$('frame-prev').addEventListener('click', () => seekFrame(Number(frame.value) - 1))
$('frame-next').addEventListener('click', () => seekFrame(Number(frame.value) + 1))
video.addEventListener('loadedmetadata', updateControls)
function syncFrame() {
  if (!activeClip || playback || video.seeking) return
  frame.value = Math.min(activeClip.frames - 1, Math.floor(video.currentTime * fps()))
  readFrame()
}
video.addEventListener('timeupdate', syncFrame)
video.addEventListener('pause', syncFrame)
video.addEventListener('seeked', syncFrame)
video.addEventListener('error', () => {
  if (activeClip) show('viewer-message', 'The clip could not play. Open it again to retry.')
})
video.addEventListener('ended', () => {
  if (!playback) return
  if (++playback.index < playback.shots.length) playPlacement()
  else openClip(activeClip, activeShot)
})
$('use-frame').addEventListener('click', () => act(async () => {
  const index = Number(frame.value)
  video.pause()
  const image = await api('/frames', { video_asset_id: activeClip.id, frame: index, label: `${activeClip.label} · frame ${index + 1}` })
  imageId = image.id
  warnedCheck = undefined
  await refresh()
  show('generation-message', `Frame ${index + 1} selected as the starting image.`)
  $('compose').scrollIntoView({ block: 'start' })
  prompt.focus({ preventScroll: true })
}))
$('add').addEventListener('click', () => act(async () => {
  const entry = { id: randomId(), asset_id: activeClip.id }
  await saveShots([...state.sequence.shots, entry])
  activeShot = entry.id
  drawClips()
  show('viewer-message', 'Added to sequence.')
}))
$('move-left').addEventListener('click', () => editShot(-1))
$('move-right').addEventListener('click', () => editShot(1))
$('remove').addEventListener('click', () => editShot(0))
$('play-sequence').addEventListener('click', () => {
  playback = { shots: [...state.sequence.shots], index: 0 }
  playPlacement()
  $('viewer-title').scrollIntoView({ block: 'start' })
})
$('export').addEventListener('click', () => act(async () => {
  state = await api('/sequence/export', { expected_revision: state.sequence.revision })
  render()
}))

async function poll() {
  try {
    if (!busy) await refresh()
  } catch {
    online = false
    $('connection').textContent = 'Connection lost · retrying'
    $('connection').dataset.online = 'false'
  } finally {
    setTimeout(poll, 2500)
  }
}
void poll()
