from pathlib import Path
from piper import PiperVoice,SynthesisConfig
import json,wave
B=Path('/workspace/work/youtube-2026-10-26/production');voice=PiperVoice.load('/workspace/work/youtube-production/models/en_US-ljspeech-high.onnx');cfg=SynthesisConfig(length_scale=1.02,noise_scale=.5,noise_w_scale=.65)
for cid in ['td-y004','vw-y004']:
 P=B/cid;previous={r['index']:r for r in json.loads((P/'timing.json').read_text())} if (P/'timing.json').exists() else {};rows=[]
 for i,s in enumerate((P/'narration.txt').read_text().strip().split('\n\n')):
  path=P/f'voice-{i:02}.wav'
  if not path.exists() or previous.get(i,{}).get('text')!=s:
   with wave.open(str(path),'wb') as f:voice.synthesize_wav(s,f,cfg)
  with wave.open(str(path),'rb') as f:sec=f.getnframes()/f.getframerate()
  rows.append({'index':i,'text':s,'wav':path.name,'seconds':sec})
 (P/'timing.json').write_text(json.dumps(rows,indent=2)+'\n');print(cid,round(sum(x['seconds'] for x in rows),2),flush=True)
