import json,base64,urllib.request,urllib.error,subprocess
from pathlib import Path
from last_light_radio.video_tools import ffmpeg_path
root=Path('artifacts/lighthouse-20261117');base='http://127.0.0.1:8769'
def api(p,d=None):
 r=urllib.request.Request(base+p,data=None if d is None else json.dumps(d).encode(),headers={'Content-Type':'application/json','X-LLR-Client':'studio'})
 try:return json.load(urllib.request.urlopen(r,timeout=180))
 except urllib.error.HTTPError as e:print(e.read().decode());raise
def save(n,d):(root/n).write_text(json.dumps(d,indent=2),encoding='utf8')
inputs=[];filters=[]
for i,(name,start,dur) in enumerate([('L01',6,120),('L02',12,120),('L03',0,84),('L04',4,120)]):
 inputs+=['-i',str(root/(name+'.mp4'))];sec=dur/24
 filters.append(f'[{i}:a]atrim=start={start/24}:duration={sec},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={sec},afade=t=in:d=0.03,afade=t=out:st={sec-.03}:d=0.03[a{i}]')
filters.append(''.join(f'[a{i}]' for i in range(4))+'concat=n=4:v=0:a=1[a]')
wav=root/'lighthouse-original-audio-corrected.wav'
subprocess.run([ffmpeg_path(),'-y',*inputs,'-filter_complex',';'.join(filters),'-map','[a]','-c:a','pcm_s24le',str(wav)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
a=api('/api/audio/import',{'audio_base64':base64.b64encode(wav.read_bytes()).decode(),'filename':wav.name,'label':'Lighthouse matched original shot sound','provenance':{'trim_frames':[[6,120],[12,120],[0,84],[4,120]],'fps':24,'edge_fade_seconds':.03}})
if a['status']!='approved':a=api('/api/audio/'+a['id']+'/review',{'decision':'approved','expected_version':a['version'],'notes':'Technical candidate soundtrack, not user-approved final.'})
p=json.loads((root/'edit-manifest.json').read_text());p['shots'][-1]['source_in_frame']=4;p['audio_tracks'][0]['asset_id']=a['id']
s=json.loads((root/'sequence-created.json').read_text());p['expected_revision']=api('/api/film/sequences/'+s['id'])['revision']
s=api('/api/film/sequences/'+s['id'],p);save('sequence-saved.json',s);save('edit-manifest-corrected.json',p)
s=api('/api/film/sequences/'+s['id']+'/export',{'expected_revision':s['revision']});save('export-started.json',s)
print(json.dumps({'id':s['id'],'export':s['export']}))
