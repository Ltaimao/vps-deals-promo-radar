from pathlib import Path
from faster_whisper import WhisperModel
import json,subprocess,re,difflib
import numpy as np
P=Path('/workspace/work/youtube-production/vw-y001')
# Concatenate original narration so ASR can be checked while the video encodes.
(P/'audio-concat.txt').write_text(''.join("file '"+str(P/f'voice-{i:02}.wav')+"'\n" for i in range(7)))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(P/'audio-concat.txt'),str(P/'narration.wav')],check=True)
m=WhisperModel('base.en',device='cpu',compute_type='int8',download_root='/workspace/work/youtube-production/models')
audio=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(P/'vw-y001.mp4'),'-f','f32le','-ac','1','-ar','16000','pipe:1']),dtype=np.float32)
segments,info=m.transcribe(audio,beam_size=5,word_timestamps=True)
rows=[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in s.words]} for s in segments]
transcript=' '.join(s['text'].strip() for s in rows);a=re.findall(r'\w+', (P/'narration.txt').read_text().lower());b=re.findall(r'\w+',transcript.lower());ratio=difflib.SequenceMatcher(None,a,b).ratio()
(P/'asr.json').write_text(json.dumps({'model':'base.en','device':'cpu/int8','language':info.language,'text':transcript,'wordSequenceSimilarity':ratio,'segments':rows,'limitation':'Automated transcription and signal/decode review, not human audition.'},indent=2)+'\n');print(json.dumps({'similarity':ratio,'text':transcript}))
