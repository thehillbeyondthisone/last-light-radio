"""Bounded one-use whole-song upload tickets, held only in this studio process."""
import copy
import secrets
import tempfile
import time
from pathlib import Path
from . import audio_tracks
from .studio import StudioError, text
from .store import canonical_bytes

TTL = 900

def begin(studio, payload):
    filename = text(payload.get('filename'), 'WAV filename', 200)
    if any(c in filename for c in ('/', '\\', ':')) or filename in ('.','..'): raise StudioError('Use a plain WAV filename')
    if Path(filename).suffix.lower() != '.wav': raise StudioError('Choose a WAV file')
    label = text(payload.get('label',filename), 'Audio label', 200)
    provenance = payload.get('provenance',{})
    if not isinstance(provenance,dict) or len(canonical_bytes(provenance))>12000:
        raise StudioError('Audio provenance must be a small JSON object')
    size=payload.get('bytes')
    if type(size) is not int or not 44<=size<=audio_tracks.FILE_LIMIT:
        raise StudioError('Choose a WAV up to 256 MiB',413)
    with studio.lock:
        tickets=getattr(studio,'audio_upload_tickets',{})
        tickets={key:value for key,value in tickets.items() if value['expires']>time.monotonic()}
        if len(tickets)>=16: raise StudioError('Too many pending audio uploads',429)
        token=secrets.token_hex(24)
        tickets[token]={'filename':filename,'label':label,'provenance':copy.deepcopy(provenance),'bytes':size,'expires':time.monotonic()+TTL}
        studio.audio_upload_tickets=tickets
    return {'upload_id':token,'upload_url':f'/api/audio/uploads/{token}/content','max_bytes':audio_tracks.FILE_LIMIT,'expires_in_seconds':TTL}

def receive(studio, token, stream, length):
    with studio.lock:
        ticket=getattr(studio,'audio_upload_tickets',{}).pop(token,None)
    if not ticket or ticket['expires']<=time.monotonic(): raise StudioError('Audio upload ticket expired or already used',409)
    if type(length) is not int or length!=ticket['bytes']: raise StudioError('Audio upload length differs from the declared file',400)
    with studio.lock:
        active=getattr(studio,'audio_upload_active',0)
        if active>=2: raise StudioError('Two audio uploads are already processing; retry with a new ticket later',429)
        studio.audio_upload_active=active+1
    try:
        with tempfile.TemporaryDirectory(prefix='audio-upload-',dir=studio.store.root) as temporary:
            path=Path(temporary)/'incoming.wav'
            with path.open('wb') as output:
                remaining=length
                while remaining:
                    block=stream.read(min(1024*1024,remaining))
                    if not block: raise StudioError('Audio upload ended before the declared file length',400)
                    if len(block)>remaining: raise StudioError('Audio upload exceeded the declared file length',400)
                    output.write(block);remaining-=len(block)
            return audio_tracks.import_file(studio,path,ticket['filename'],ticket['label'],ticket['provenance'])
    finally:
        with studio.lock: studio.audio_upload_active-=1
