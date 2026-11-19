import json,base64,urllib.request,subprocess,time
from pathlib import Path
from last_light_radio.video_tools import ffmpeg_path
root=Path('artifacts/lighthouse-20261117');root.mkdir(parents=True,exist_ok=True)
base='http://127.0.0.1:8769'
def api(p,d=None):
 r=urllib.request.Request(base+p,data=None if d is None else json.dumps(d).encode(),headers={'Content-Type':'application/json','X-LLR-Client':'studio'})
 return json.load(urllib.request.urlopen(r,timeout=180))
def save(n,d): (root/n).write_text(json.dumps(d,indent=2),encoding='utf-8')
listing=api('/api/film')
assert not any(p.get('title')=='The Uncharted Light' for p in listing['projects']), 'Project already exists; inspect before retry'
shots=[]; inputs=[]; filters=[]
notes='Technical acceptance for experimental candidate cut, not user-approved final. Set geography drifts; L03 requested reverse still shows window.'
for idx,(name,start,dur) in enumerate([('L01',6,120),('L02',12,120),('L03',0,84),('L04',6,120)]):
 file=root/(name+'.mp4');url='http://192.168.1.168:8188/view?filename='+name+'_00001_.mp4&subfolder=lighthouse-20261117&type=output'
 urllib.request.urlretrieve(url,file)
 asset=api('/api/film/assets/import',{'video_base64':base64.b64encode(file.read_bytes()).decode(),'filename':file.name,'label':name+' Lighthouse candidate','provenance':{'source_url':url,'kind':'local_H3_SD_experiment','limitations':notes}})
 save(name+'-import.json',asset)
 if asset['status']!='approved': asset=api('/api/film/assets/'+asset['id']+'/review',{'decision':'approved','expected_version':asset['version'],'notes':notes})
 shots.append({'id':name,'asset_id':asset['id'],'source_in_frame':start,'duration_frames':dur})
 inputs+=['-i',str(file)]; sec=dur/24
 filters.append(f'[{idx}:a]atrim=start={start/24}:duration={sec},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.03,afade=t=out:st={sec-.03}:d=0.03[a{idx}]')
filters.append(''.join(f'[a{i}]' for i in range(4))+'concat=n=4:v=0:a=1[a]')
wav=root/'lighthouse-original-audio.wav'
subprocess.run([ffmpeg_path(),'-y',*inputs,'-filter_complex',';'.join(filters),'-map','[a]','-c:a','pcm_s24le',str(wav)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
audio=api('/api/audio/import',{'audio_base64':base64.b64encode(wav.read_bytes()).decode(),'filename':wav.name,'label':'Lighthouse original generated shot sound','provenance':{'kind':'matched_source_audio','trim_frames':[[6,120],[12,120],[0,84],[6,120]],'fps':24,'edge_fade_seconds':.03}})
save('audio-import.json',audio)
if audio['status']!='approved': audio=api('/api/audio/'+audio['id']+'/review',{'decision':'approved','expected_version':audio['version'],'notes':notes})
project=api('/api/film/projects',{'title':'The Uncharted Light'});save('project.json',project)
seq=api('/api/film/projects/'+project['id']+'/sequences',{'title':'Lighthouse — candidate v1'});save('sequence-created.json',seq)
payload={'expected_revision':seq['revision'],'title':'Lighthouse — candidate v1','width':672,'height':384,'shots':shots,'audio_tracks':[{'id':'generated-sound','asset_id':audio['id'],'role':'production','start_frame':0,'source_in_frame':0,'duration_frames':444,'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}]}
save('edit-manifest.json',payload)
seq=api('/api/film/sequences/'+seq['id'],payload);save('sequence-saved.json',seq)
seq=api('/api/film/sequences/'+seq['id']+'/export',{'expected_revision':seq['revision']});save('export-started.json',seq)
print(json.dumps({'project_id':project['id'],'sequence_id':seq['id'],'export':seq['export']},indent=2))

