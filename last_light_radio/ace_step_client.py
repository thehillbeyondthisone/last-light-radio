"""Strict loopback-only client for the inspected Pinokio ACE-Step Gradio API."""
import json
import hashlib
import time
import re
from pathlib import PureWindowsPath, Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from .comfy import ComfyError

OUTPUT_ROOT = PureWindowsPath(r'C:\pinokio\api\ace-step-ui.pinokio.git\app\ACE-Step-1.5\acestep\ui\gradio_outputs')

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def normalize_url(value):
    if not isinstance(value,str):raise ComfyError('INVALID_URL','Use the verified local ACE-Step API URL')
    parsed=urlsplit(value)
    try:port=parsed.port
    except ValueError:raise ComfyError('INVALID_URL','Invalid ACE-Step port') from None
    if (parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or not port
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}):
        raise ComfyError('INVALID_URL','ACE-Step must use an explicit HTTP loopback host and port, without credentials or paths')
    return value.rstrip('/')

def task_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value):
        raise ComfyError('INVALID_TASK_ID','ACE-Step did not return a valid task identity')
    return value

class AceClient:
    def __init__(self,base_url,timeout=10):
        self.base_url=normalize_url(base_url);self.timeout=timeout
        self.opener=build_opener(ProxyHandler({}),_NoRedirect())
    def _request(self,method,path,payload=None,*,timeout=None,limit=4*1024*1024,submission=False):
        if not path.startswith('/') or path.startswith('//'):raise ComfyError('UNSAFE_URL','ACE-Step requests must stay on the selected service')
        data=json.dumps(payload,allow_nan=False).encode() if payload is not None else None
        request=Request(self.base_url+path,data=data,method=method,headers={'Accept':'application/json','Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=timeout or self.timeout) as response:
                body=response.read(limit+1)
                if len(body)>limit:raise ComfyError('SUBMISSION_AMBIGUOUS' if submission else 'RESPONSE_TOO_LARGE','ACE-Step response exceeded the safe size limit')
                return dict(response.headers.items()),body
        except HTTPError as error:
            if submission and error.code not in {400,401,403,404,422,429}:
                raise ComfyError('SUBMISSION_AMBIGUOUS','ACE-Step did not confirm a task ID; do not submit again automatically',status=error.code) from error
            raise ComfyError('HTTP_ERROR','ACE-Step returned an HTTP error',status=error.code) from error
        except (URLError,OSError,TimeoutError) as error:
            raise ComfyError('SUBMISSION_AMBIGUOUS' if submission else 'SERVICE_UNAVAILABLE',
                             'ACE-Step response was lost; task acceptance is unknown' if submission else 'ACE-Step is unavailable at the selected loopback endpoint',reason=str(error)) from error
    def _json(self,method,path,payload=None,*,submission=False,timeout=None):
        _,body=self._request(method,path,payload,submission=submission,timeout=timeout)
        try:record=json.loads(body)
        except (ValueError,UnicodeError) as error:
            raise ComfyError('SUBMISSION_AMBIGUOUS' if submission else 'INVALID_RESPONSE','ACE-Step did not return valid JSON') from error
        if not isinstance(record,dict) or record.get('code')!=200 or record.get('error') is not None:
            raise ComfyError('SUBMISSION_AMBIGUOUS' if submission else 'INVALID_RESPONSE','ACE-Step response did not confirm success',response=record)
        return record
    def probe(self):
        health=self._json('GET','/health');models=self._json('GET','/v1/models')
        return {'health':health,'models':models}
    def submit(self,request):
        # The inspected Gradio endpoint returns its task ID only after generation.
        response=self._json('POST','/release_task',request,submission=True,timeout=1800 if request.get("audio_duration",30)>30 else 300)
        data=response.get('data')
        try:
            if not isinstance(data,dict) or data.get('status')!='succeeded':raise ValueError('Unexpected task status')
            task_id(data.get('task_id'))
        except (ValueError,ComfyError) as error:
            raise ComfyError('SUBMISSION_AMBIGUOUS','ACE-Step did not confirm its completed task ID',response=response) from error
        return response
    def poll(self,identity):
        identity=task_id(identity)
        response=self._json('POST','/query_result',{'task_id_list':[identity]})
        rows=response.get('data')
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('task_id')!=identity:
            raise ComfyError('TASK_ID_MISMATCH','ACE-Step returned a different task result')
        row=rows[0]
        if type(row.get('status')) is not int or row['status'] not in {0,1}:
            raise ComfyError('INVALID_RESPONSE','Unsupported ACE-Step task status')
        return response
    def _audio_url(self,result):
        if not isinstance(result,dict) or not isinstance(result.get('url'),str) or not isinstance(result.get('file'),str):
            raise ComfyError('INVALID_AUDIO_REFERENCE','Expected the owned result WAV URL and source path')
        url=urlsplit(result['url'])
        values=parse_qs(url.query,keep_blank_values=True)
        if url.scheme or url.netloc or url.fragment or url.path!='/v1/audio' or set(values)!={'path'} or len(values['path'])!=1:
            raise ComfyError('UNSAFE_AUDIO_URL','Audio download must use only the same-service /v1/audio result URL')
        source=PureWindowsPath(result['file']);linked=PureWindowsPath(values['path'][0])
        try:parts=source.relative_to(OUTPUT_ROOT).parts
        except ValueError:raise ComfyError('UNSAFE_AUDIO_PATH','Result is outside the verified ACE-Step output directory') from None
        if (source!=linked or len(parts)!=2 or not re.fullmatch(r'api_[0-9]+',parts[0])
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.wav',parts[1]) or '..' in source.parts):
            raise ComfyError('UNSAFE_AUDIO_PATH','Returned WAV path does not match the owned result URL')
        return result['url']

    def download(self,result):
        self._audio_url(result)
        headers,data=self._request('GET',result['url'],limit=20*1024*1024)
        headers={key.lower():value for key,value in headers.items()}
        mime=headers.get('content-type','').split(';')[0].strip().lower()
        if (mime not in {'audio/wav','audio/x-wav','audio/wave','application/octet-stream'} or len(data)<44
                or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE'):
            raise ComfyError('INVALID_AUDIO_MEDIA','ACE-Step download is not the expected WAV container')
        return data


    def download_to(self, result, destination, limit=256*1024*1024):
        """Bounded streaming of a validated same-service WAV; no full-file RAM copy."""
        url=self._audio_url(result);destination=Path(destination);created=False
        try:
            with self.opener.open(Request(self.base_url+url,headers={'Accept':'audio/wav'}),timeout=30) as response:
                headers={k.lower():v for k,v in response.headers.items()}
                mime=headers.get('content-type','').split(';')[0].strip().lower()
                if mime not in {'audio/wav','audio/x-wav','audio/wave','application/octet-stream'}:
                    raise ComfyError('INVALID_AUDIO_MEDIA','ACE-Step result is not WAV media')
                length=headers.get('content-length')
                if length is not None and (not length.isdigit() or not 44<=int(length)<=limit):
                    raise ComfyError('INVALID_AUDIO_LENGTH','ACE-Step WAV length exceeds the bounded download size')
                digest=hashlib.sha256();size=0;header=b'';started=time.monotonic()
                with destination.open('xb') as output:
                    created=True
                    while True:
                        if time.monotonic()-started>600:raise ComfyError('DOWNLOAD_TIMEOUT','Music download exceeded its bounded time budget')
                        chunk=response.read(min(1024*1024,limit-size+1))
                        if not chunk:break
                        size+=len(chunk)
                        if size>limit:raise ComfyError('RESPONSE_TOO_LARGE','Generated WAV exceeds the 256 MiB limit')
                        if len(header)<12:header=(header+chunk)[:12]
                        output.write(chunk);digest.update(chunk)
                if size<44 or header[:4]!=b'RIFF' or header[8:12]!=b'WAVE' or (length is not None and size!=int(length)):
                    raise ComfyError('INVALID_AUDIO_MEDIA','Generated WAV header or transfer length is invalid')
                return {'sha256':digest.hexdigest(),'bytes':size}
        except Exception as error:
            if created:destination.unlink(missing_ok=True)
            if isinstance(error,ComfyError):raise
            raise ComfyError('AUDIO_DOWNLOAD_FAILED','Music result download failed; the accepted task must not be resubmitted',reason=str(error)) from error
