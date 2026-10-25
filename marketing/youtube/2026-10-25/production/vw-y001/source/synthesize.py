from pathlib import Path
import json,wave,hashlib
from piper import PiperVoice,SynthesisConfig
ROOT=Path('/workspace/work/seo15/vps-deals-promo-radar-main/marketing/youtube/2026-10-25')
OUT=Path('/workspace/work/youtube-production/vw-y001');OUT.mkdir(parents=True,exist_ok=True)
s=(ROOT/'scripts/vw-y001.md').read_text().split('## Narration\n\n')[1].split('\n\n## Shot list')[0].strip()
paragraphs=s.split('\n\n')
voice=PiperVoice.load('/workspace/work/youtube-production/models/en_US-ljspeech-high.onnx')
config=SynthesisConfig(length_scale=1.02,noise_scale=.5,noise_w_scale=.65)
previous={r["index"]:r for r in json.loads((OUT/"timing.json").read_text())} if (OUT/"timing.json").exists() else {}
records=[]
for i,text in enumerate(paragraphs):
 p=OUT/f'voice-{i:02}.wav'
 if not p.exists() or previous.get(i,{}).get('text')!=text:
  with wave.open(str(p),'wb') as w:voice.synthesize_wav(text,w,config)
 with wave.open(str(p),'rb') as w:seconds=w.getnframes()/w.getframerate()
 records.append({'index':i,'text':text,'wav':p.name,'seconds':seconds})
(OUT/'narration.txt').write_text(s+'\n');(OUT/'timing.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'segments':len(records),'spokenSeconds':round(sum(r['seconds'] for r in records),2),'voice':'en_US-ljspeech-high','licenseSource':'https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/ljspeech/high/MODEL_CARD','datasetLicense':'public domain'}))
