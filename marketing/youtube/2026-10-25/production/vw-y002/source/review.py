from pathlib import Path
from faster_whisper import WhisperModel
from PIL import Image,ImageDraw
import numpy as np,json,subprocess,re,difflib,textwrap,sys,hashlib
B=Path('/workspace/work/youtube-ops-2026-10-25/production');m=WhisperModel('base.en',device='cpu',compute_type='int8',download_root='/workspace/work/youtube-production/models')
def stamp(t):
 ms=round(max(t,0)*1000);h,ms=divmod(ms,3600000);mi,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{mi:02}:{s:02},{ms:03}'
for cid in sys.argv[1:]:
 P=B/cid;f=P/f'{cid}.mp4';probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]));(P/'ffprobe.json').write_text(json.dumps(probe,indent=2)+'\n');audio=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(f),'-f','f32le','-ac','1','-ar','16000','pipe:1']),dtype=np.float32);segs,info=m.transcribe(audio,beam_size=5,word_timestamps=True);rows=[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in s.words]} for s in segs];transcript=' '.join(s['text'].strip() for s in rows);ref=(P/'narration.txt').read_text().replace('V P S Deals Wire dot com','vpsdealswire.com').replace('vpsdealswire dot com','vpsdealswire.com').replace('tattoodoodle dot com','tattoodoodle.com').split();words=[w for s in rows for w in s['words']];norm=lambda s:re.sub('[^a-z0-9]','',s.lower());a=[norm(w) for w in ref];b=[norm(w['word']) for w in words];similarity=difflib.SequenceMatcher(None,a,b,autojunk=False).ratio();mapping={}
 for block in difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks():
  for j in range(block.size):mapping[block.a+j]=words[block.b+j]
 for i in range(len(ref)):
  if i not in mapping:
   l=max((j for j in mapping if j<i),default=None);r=min((j for j in mapping if j>i),default=None)
   if l is not None and r is not None:t=mapping[l]['end']+(mapping[r]['start']-mapping[l]['end'])*(i-l)/(r-l)
   elif l is not None:t=mapping[l]['end']+.12
   else:t=0
   mapping[i]={'start':t,'end':t+.18}
 cues=[];k=0
 while k<len(ref):
  end=k+1
  while end<len(ref) and end-k<12 and len(' '.join(ref[k:end+1]))<80 and not(end-k>=5 and ref[end-1].endswith(('.','?','!'))):end+=1
  while end-k>5 and re.sub('[^a-z]','',ref[end-1].lower())in {'a','the','of','and','to','with','for','your','our','its','is','do','not','from','by','more','than','what','how','this','different'}:end-=1
  line=' '.join(ref[k:end]).replace('tattoodoodle dot com','tattoodoodle.com').replace('vpsdealswire dot com','vpsdealswire.com').replace('V P S Deals Wire dot com','vpsdealswire.com');start=max(0,mapping[k]['start']);finish=max(start+.4,mapping[end-1]['end']);cues.append((start,finish,'\n'.join(textwrap.wrap(line,width=43))));k=end
 srt='\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{t}'for i,(a,b,t)in enumerate(cues))+'\n';(P/f'{cid}.en.srt').write_text(srt)
 asr={'model':'base.en','mediaSha256':hashlib.sha256(f.read_bytes()).hexdigest(),'tokenNormalization':'Canonical domain spelling in source text before whitespace-token comparison; this is not a WER or human-listening score.','method':'Actual encoded final audio decoded to 16kHz float32; automatic transcription, no human audition claimed.','language':info.language,'wordSequenceSimilarity':similarity,'text':transcript,'segments':rows};(P/'asr.json').write_text(json.dumps(asr,indent=2)+'\n')
 res=subprocess.run(['ffmpeg','-hide_banner','-i',str(f),'-af','volumedetect','-f','null','-'],capture_output=True);(P/'audio-levels.log').write_text(res.stderr.decode());assert res.returncode==0
 duration=float(probe['format']['duration']);short=cid.endswith('003');ts=[duration*x for x in ([.12,.51,.87] if short else [.04,.18,.30,.37,.43,.54,.68,.82,.95])];w,h=(270,480)if short else(480,270);contact=Image.new('RGB',(w*3,h*((len(ts)+2)//3)),'white');d=ImageDraw.Draw(contact)
 for j,t in enumerate(ts):
  jpg=P/f'final-{j:02}.jpg';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(f),'-frames:v','1',str(jpg)],check=True);im=Image.open(jpg);im.thumbnail((w,h));contact.paste(im,((j%3)*w,(j//3)*h));d.text(((j%3)*w+5,(j//3)*h+5),f'{t:.1f}s',fill='#783F42'if cid.startswith('td')else'white')
 contact.save(P/'final-contact.jpg');print(json.dumps({'id':cid,'seconds':duration,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'similarity':similarity,'transcript':transcript}),flush=True)
