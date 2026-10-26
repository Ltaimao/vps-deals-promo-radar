from pathlib import Path
from PIL import Image,ImageDraw
import subprocess,json
B=Path('/workspace/work/youtube-2026-10-26/production')
for cid in ['td-y004','vw-y004']:
 P=B/cid;timing=json.loads((P/'video-timing.json').read_text());sheet=Image.new('RGB',(1440,270*((len(timing)+2)//3)),'white');d=ImageDraw.Draw(sheet)
 for j,r in enumerate(timing):
  t=(r['videoStart']+r['videoEnd'])/2;p=P/f'inspect-{j:02}.png';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(P/f'{cid}.mp4'),'-frames:v','1',str(p)],check=True);im=Image.open(p);im.thumbnail((480,270));sheet.paste(im,((j%3)*480,(j//3)*270));d.text(((j%3)*480+5,(j//3)*270+5),f'{j+1}: {t:.1f}s',fill='red')
 sheet.save(P/'scene-review.jpg',quality=95);m=Image.open(P/'thumbnail.jpg');m.resize((320,180),Image.Resampling.LANCZOS).save(P/'thumbnail-mobile.png')
