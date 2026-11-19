import { useEffect, useState } from 'react'
import { api } from './api'
type Wave={peaks:number[];bins:number;sample_count:number;sample_rate:number;duration_seconds:number;source_sha256:string}
export default function AudioWaveform({assetId,sourceIn=0,duration,onSeek,compact=false}:{assetId:string;sourceIn?:number;duration?:number;onSeek?:(seconds:number)=>void;compact?:boolean}){
 const [wave,setWave]=useState<Wave|null>(null),[error,setError]=useState('')
 useEffect(()=>{let live=true;setWave(null);setError('');api<Wave>(`film/audio/${assetId}/waveform`).then(w=>{if(live)setWave(w)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[assetId])
 if(error)return <small title={error}>Waveform unavailable</small>
 if(!wave)return <small>Loading waveform…</small>
 const end=Math.min(wave.duration_seconds,sourceIn+(duration??wave.duration_seconds)),count=wave.peaks.length
 const first=Math.floor(sourceIn/wave.duration_seconds*count),last=Math.max(first+1,Math.ceil(end/wave.duration_seconds*count)),peaks=wave.peaks.slice(first,last)
 return <svg role="img" aria-label="Waveform from actual audio samples" viewBox={`0 0 ${Math.max(1,peaks.length)} 40`} preserveAspectRatio="none" style={{width:'100%',height:compact?22:65,display:'block',background:'#18252a',cursor:onSeek?'crosshair':undefined}} onClick={e=>{if(onSeek){e.stopPropagation();const r=e.currentTarget.getBoundingClientRect();onSeek(sourceIn+Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*(end-sourceIn))}}}><title>Actual decoded audio peaks; click to seek when enabled</title>{peaks.map((p,i)=><line key={i} x1={i} x2={i} y1={20-Math.max(0,Math.min(1,p))*19} y2={20+Math.max(0,Math.min(1,p))*19} stroke="#91c5ac" strokeWidth="1"/>)}</svg>
}

