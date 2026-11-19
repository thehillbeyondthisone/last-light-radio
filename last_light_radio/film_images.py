"""Immutable image conditioning sources; never promote a generated candidate."""
import base64
import binascii
import io
import json
import re
import subprocess
import warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from . import film
from .studio import StudioError, text
from .store import sha256, canonical_bytes
from .generation import utc_now
from .video_tools import ffmpeg_path

LIMIT=20*1024*1024

def get(studio, identity):
    if not isinstance(identity,str) or not re.fullmatch(r'image\.[0-9a-f]{64}',identity):raise StudioError('Image source not found',404)
    record=film._read(studio,'film.image.'+identity)
    return {**record,'media_url':f'/api/film/images/{identity}/media'}

def verify(studio,identity):
    record=get(studio,identity)
    for key in ('source','png'):studio.store.verify_master({'id':identity,**record[key]})
    return record

def listing(studio):return {'images':[get(studio,r['id']) for r in film._records(studio,'film.image.')]}

def import_bytes(studio,data,filename,label,provenance, *, clip_upload=False):
    if not data or len(data)>LIMIT:raise StudioError('Choose an image of at most 20 MiB')
    if not isinstance(provenance,dict) or len(canonical_bytes(provenance))>12000:raise StudioError('Image provenance is too large')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(data))
            formats = {'PNG', 'JPEG', 'WEBP', 'AVIF'} if clip_upload else {'PNG', 'JPEG', 'WEBP'}
            if image.format not in formats:
                raise ValueError('Choose a still PNG, JPEG, WebP or AVIF' if clip_upload else 'Use a still PNG, JPEG or WebP')
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Choose a still image. Animated images are unsupported')
            megapixels = 64 if clip_upload else 16
            pixel_limit = 64_000_000 if clip_upload else 16_777_216
            if image.width * image.height > pixel_limit:
                raise ValueError(f'Choose an image up to {megapixels} megapixels')
            if clip_upload:
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            else:
                image = ImageOps.exif_transpose(image)
            image = image.convert('RGB')
            output=io.BytesIO();image.save(output,format='PNG');png=output.getvalue()
    except UnidentifiedImageError:
        raise StudioError('Could not open the image. Export it as JPEG or PNG and upload it again.') from None
    except Exception as error:raise StudioError('Invalid conditioning image: '+str(error)) from None
    if len(png)>LIMIT:raise StudioError('Decoded image exceeds the 20 MiB upload limit')
    digest=sha256(data);identity='image.'+digest
    with studio.lock,studio.db() as db:
        prior=studio.setting('film.image.'+identity)
        if prior:return get(studio,identity)
        source={'path':f'film/images/{digest}/original.bin','sha256':digest}
        derivative={'path':f'film/images/{digest}/conditioning.png','sha256':sha256(png)}
        studio.store.write_once(source['path'],data);studio.store.write_once(derivative['path'],png)
        record={'id':identity,'label':text(label,'Image label',200),'filename':text(filename,'Image filename',200),
                'created':utc_now(),'width':image.width,'height':image.height,'source':source,'png':derivative,
                'provenance':provenance,'usage':'conditioning source, not production approval'}
        studio.store.save_snapshot(record);film._write(db,'film.image.'+identity,record)
    return get(studio,identity)

def import_image(studio,payload, *, clip_upload=False):
    encoded=payload.get('image_base64')
    if not isinstance(encoded,str) or len(encoded)>LIMIT*4//3+8:raise StudioError('Choose an image up to 20 MiB')
    try:data=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise StudioError('Invalid image upload') from None
    return import_bytes(studio,data,payload.get('filename','image.png'),payload.get('label','Image reference'),
                        payload.get('provenance',{}),clip_upload=clip_upload)

def from_frame(studio,payload):
    asset=film.asset(studio,payload.get('video_asset_id'))
    frame=payload.get('frame')
    if type(frame) is not int or not 0<=frame<asset['frame_count']:raise StudioError('Choose a source frame on the 24 fps Film clock')
    path=film.asset_media(studio,asset['id'])
    result=subprocess.run([ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),
        '-vf',f'fps=24,select=eq(n\\,{frame})','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,timeout=120)
    if result.returncode or not result.stdout:raise StudioError('Source frame extraction failed')
    provenance={'kind':'film_source_frame','video_asset_id':asset['id'],'source':asset['source'],
                'frame':frame,'frame_rate':24,'time_seconds':frame/24,'clock':'Film fps=24 resampled source clock',
                'source_review_status':asset['status'],'source_review_version':asset['version'],
                'source_receipt':studio.store.save_snapshot(asset)}
    return import_bytes(studio,result.stdout,'source-frame.png',payload.get('label',asset['label']+f' frame {frame}'),provenance)

def reference_parameters(value):
    """Normalize ordered model inputs; roles are explicit human-authored instructions."""
    if not isinstance(value, list) or not 1 <= len(value) <= 9:
        raise StudioError('Reference-to-video needs one to nine ordered images')
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {'image_id', 'role'}:
            raise StudioError('Each reference image needs image_id and role')
        identity = text(item.get('image_id'), 'Reference image ID', 100)
        if not re.fullmatch(r'image\.[0-9a-f]{64}', identity):
            raise StudioError('Use an imported reference image ID')
        if identity in seen: raise StudioError('Do not repeat the same image in multiple reference slots')
        seen.add(identity)
        result.append({'image_id': identity, 'role': text(item.get('role'), 'Reference image role', 1400)})
    return result


def references(studio,params):
    if params.get('reference_images'):
        return {'reference_'+str(i+1): verify(studio, item['image_id'])
                for i,item in enumerate(reference_parameters(params['reference_images']))}
    return {role:verify(studio,params[key]) for role,key in [('first_frame','first_frame_id'),('last_frame','last_frame_id')] if params.get(key)}


def reference_node(role):
    if role == 'first_frame': return '18'
    if role == 'last_frame': return '19'
    if re.fullmatch(r'reference_[1-9]', role): return str(17 + int(role.split('_')[1]))
    raise StudioError('Unknown image conditioning role')


def prepare(studio,graph,params,prefix):
    refs=references(studio,params)
    for role,record in refs.items():
        node=reference_node(role)
        graph[node]={'class_type':'LoadImage','inputs':{'image':prefix+'/'+role+'.png'}}
        key = 'ref_images.ref_image_'+str(int(role.split('_')[1])-1) if role.startswith('reference_') else role
        graph['6']['inputs'][key]=[node,0]
    if params.get('reference_images'):
        # Roles live in the actual conditioning prompt, not only in UI metadata.
        graph['6']['inputs']['prompt'] += '\n\nReference input roles:\n' + '\n'.join(
            '<Picture '+str(i+1)+'>: '+item['role'] for i,item in enumerate(params['reference_images']))
    return graph,refs
