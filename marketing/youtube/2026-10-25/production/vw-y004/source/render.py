from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops,ImageOps
import json,subprocess
B=Path('/workspace/work/youtube-2026-10-26/production');F=Path('/usr/share/fonts/truetype/dejavu')
TD={'bg':'#F7F4EE','panel':'#FFFDFA','ink':'#171717','muted':'#756F67','accent':'#783F42','line':'#D9D1C5','brand':'TATTOO DOODLE','domain':'tattoodoodle.com'}
VW={'bg':'#101D2B','panel':'#192B3D','ink':'#F4F7F8','muted':'#ACBDCB','accent':'#65D9C4','line':'#355063','brand':'VPS DEALS WIRE','domain':'vpsdealswire.com'}
def font(n,b=False,serif=False):return ImageFont.truetype(str(F/(('DejaVuSerif' if serif else 'DejaVuSans')+('-Bold' if b else '')+'.ttf')),n)
def txt(d,xy,s,n=32,c=None,b=False,anchor=None,serif=False):d.text(xy,s,font=font(n,b,serif),fill=c or T['ink'],anchor=anchor)
def para(d,xy,s,w,n=30,c=None):
 x,y=xy;line=''
 for word in s.split():
  test=(line+' '+word).strip()
  if d.textlength(test,font=font(n))>w and line:txt(d,(x,y),line,n,c);y+=n*1.45;line=word
  else:line=test
 if line:txt(d,(x,y),line,n,c)
def panel(d,box):d.rounded_rectangle(box,radius=22,fill=T['panel'],outline=T['line'],width=2)
def fit(im,img,box):
 a=img.copy();a.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);pos=(box[0]+(box[2]-box[0]-a.width)//2,box[1]+(box[3]-box[1]-a.height)//2)
 if a.mode=='RGBA':im.paste(a,pos,a)
 else:im.paste(a,pos)
def base(i,title,sub):
 im=Image.new('RGB',(1920,1080),T['bg']);d=ImageDraw.Draw(im);txt(d,(80,45),T['brand']+'  /  '+('LETTERING NOTES' if T is TD else 'BUYING NOTES'),24,T['accent'],b=True);txt(d,(1840,45),f'{i+1:02} / '+('06' if P.name=='td-y004' else '07'),24,T['muted'],anchor='ra');txt(d,(80,130),title,60,b=True,serif=T is TD);txt(d,(80,223),sub,29,T['muted']);d.line((80,290,1840,290),fill=T['line'],width=2);txt(d,(80,1015),'Digital lettering references; final artwork needs artist review.' if T is TD else 'Explanatory diagrams; no benchmark performed.',23,T['muted']);txt(d,(1840,1015),T['domain'],25,T['accent'],anchor='ra');return im,d
def save(i,im):im.save(P/f'scene-{i:02}.png')
def cropink(path):
 im=Image.open(path).convert('RGBA');mask=ImageChops.multiply(ImageOps.invert(ImageOps.grayscale(im)),im.getchannel('A')).point(lambda v:255 if v>40 else 0);bb=mask.getbbox();return im.crop((max(0,bb[0]-20),max(0,bb[1]-20),min(im.width,bb[2]+20),min(im.height,bb[3]+20)))
def arrow(d,a,b):d.line((a,b),fill=T['accent'],width=6);x,y=b;d.polygon([(x,y),(x-18,y-12),(x-18,y+12)],fill=T['accent'])

def cards(i,title,sub,items):
 im,d=base(i,title,sub);gap=30;w=(1760-gap*(len(items)-1))//len(items)
 for j,(label,body)in enumerate(items):
  x=80+j*(w+gap);panel(d,(x,365,x+w,905));txt(d,(x+35,410),label,26,T['accent'],b=True);para(d,(x+35,545),body,w-70,38)
 save(i,im)
def td():
 global T,P
 T=TD;P=B/'td-y004';art=cropink(P/'lettering.png')
 im,d=base(0,'A transparent file is still a reference.','The download format does not establish a professional transfer stencil.')
 panel(d,(80,355,1160,925));fit(im,art,(145,465,1095,755));txt(d,(620,825),'ACTUAL DIGITAL EXPORT',25,T['accent'],anchor='mm');panel(d,(1230,355,1840,925));para(d,(1270,435),'What job does this file do?',520,43);para(d,(1270,695),'A clearer conversation with your artist.',520,31,T['muted']);save(0,im)
 cards(1,'Name the feature you want to discuss.','A reference can explain a direction without copying every line.',[('SUBJECT','What is the idea?'),('LETTERING','Which direction?'),('COMPOSITION','What should stay open?')])
 im,d=base(2,'Keep wording and notes together.','Actual lettering tool and genuine reference-card preview.')
 panel(d,(80,335,1260,945));panel(d,(1320,335,1840,945));txt(d,(1360,365),'ACTUAL REFERENCE CARD',23,T['accent'],b=True);fit(im,Image.open(P/'reference-dialog.png').crop((37,102,421,582)),(1360,415,1800,920));save(2,im)
 cards(3,'Leave final preparation to the artist.','Ask the studio what it needs; a public photo is not permission to copy.',[('REFERENCE','Describe what matters.'),('FINAL DRAWING','Agree with the artist.'),('PREPARATION','Studio workflow.')])
 im,d=base(4,'Make the open decision visible.','Original sample handoff note; not an artist-approved design.')
 panel(d,(80,360,1120,920));txt(d,(130,415),'SAMPLE NOTE',26,T['accent'],b=True);para(d,(130,540),'I like this open composition. I am open to your redraw.',930,50);panel(d,(1190,360,1840,920));txt(d,(1230,415),'KEEP SEPARATE',26,T['accent'],b=True);para(d,(1230,555),'Exact wording, spelling and punctuation.',560,39);save(4,im)
 im,d=base(5,'Show the reference. Ask one question.','The live guide explains the file’s role, not a tattoo procedure.')
 panel(d,(80,335,1840,945));fit(im,Image.open(P/'reference-dialog.png'),(125,365,1065,920));para(d,(1170,440),'Which format would you like for our design discussion?',610,44);para(d,(1170,775),'Reference preview shown after loading.',600,27,T['muted']);save(5,im)
 im,d=base(5,'Use the image to start a conversation.','Read the reference-versus-stencil guide.')
 panel(d,(80,335,1140,945));fit(im,Image.open(P/'guide.png'),(100,355,1120,925));txt(d,(1210,430),'THE COMPLETE GUIDE',24,T['accent'],b=True);txt(d,(1210,530),'tattoodoodle.com',42,b=True);para(d,(1210,655),'Direct guide link in the description.',560,36);para(d,(1210,825),'No physical-size or healing promise.',560,28,T['muted']);save(5,im)
 thumb=Image.new('RGB',(1280,720),T['bg']);d=ImageDraw.Draw(thumb);txt(d,(60,60),'REFERENCE',78,b=True,serif=True);txt(d,(60,160),'OR STENCIL?',78,b=True,serif=True);panel(d,(55,300,1225,610));fit(thumb,art,(110,340,1170,550));txt(d,(60,655),'Same file? Different job.  /  Tattoo Doodle',26,T['accent']);thumb.save(P/'thumbnail.jpg',quality=94)
def vw():
 global T,P
 T=VW;P=B/'vw-y004'
 cards(0,'The storage label is not a benchmark.','NVMe describes a technology; it does not report your application’s result.',[('NVMe / SSD','A plan label'),('PLAN LIMITS','Read the conditions'),('YOUR TASK','Needs its own evidence')])
 cards(1,'Start with the job your VPS must do.','Original workload examples; no workload was tested.',[('STATIC SITE','Deliver files'),('DATABASE','Read and write data'),('BUILD','Create outputs')])
 im,d=base(2,'Read the limits, not just the label.','Actual live guide recording. No provider benchmark was performed.');panel(d,(1320,335,1840,945));txt(d,(1360,405),'CHECK THE PLAN',26,T['accent'],b=True);para(d,(1360,520),'Capacity, I/O limits and provider policy.',430,37);para(d,(1360,785),'Undocumented? Record the gap.',430,28,T['muted']);save(2,im)
 im,d=base(3,'Capacity and speed are different questions.','These are definitions to verify, not measured values.')
 for j,(label,body)in enumerate([('CAPACITY','How much data?'),('IOPS','Operations per second'),('THROUGHPUT','Data per second'),('LATENCY','Time for an operation')]):
  x=80+(j%2)*900;y=350+(j//2)*300;panel(d,(x,y,x+860,y+260));txt(d,(x+35,y+35),label,28,T['accent'],b=True);txt(d,(x+35,y+125),body,38)
 save(3,im)
 im,d=base(4,'Ask about the constraint that matters.','Original support-question example; no provider answer is implied.');panel(d,(80,365,1840,910));txt(d,(130,420),'A USEFUL QUESTION',28,T['accent'],b=True);para(d,(130,555),'Which storage limit applies to this plan and my intended workload?',1620,57);save(4,im)
 im,d=base(5,'An evaluation plan is not a test result.','Nothing here reports an executed storage benchmark.');panel(d,(80,350,1840,940))
 for j,(a,b)in enumerate([('Workload','Define the real task'),('Permission','Read current provider terms'),('Method','Choose a relevant check'),('Result','NOT RUN')]):
  y=390+j*130;txt(d,(130,y),a.upper(),26,T['accent'],b=True);txt(d,(650,y),b,37);d.line((130,y+88,1790,y+88),fill=T['line'],width=2)
 save(5,im)
 im,d=base(6,'Build a shortlist around your workload.','The storage guide gives you a practical checklist.');panel(d,(80,335,1140,945));fit(im,Image.open(P/'guide.png'),(100,355,1120,925));txt(d,(1210,430),'THE COMPLETE GUIDE',24,T['accent'],b=True);txt(d,(1210,530),'vpsdealswire.com',42,b=True);para(d,(1210,660),'Direct guide link in the description.',550,36);para(d,(1210,825),'Confirm current plan documentation.',550,28,T['muted']);save(6,im)
 thumb=Image.new('RGB',(1280,720),T['bg']);d=ImageDraw.Draw(thumb);txt(d,(60,55),'NVMe = FAST?',82,b=True);txt(d,(60,165),'Ask about the limit.',43,T['accent']);
 for j,(a,b)in enumerate([('LABEL','NVMe'),('LIMITS','Check'),('RESULT','Not tested')]):
  x=55+j*410;panel(d,(x,320,x+390,585));txt(d,(x+25,355),a,26,T['accent'],b=True);txt(d,(x+25,455),b,39)
 txt(d,(60,655),'Storage buying notes  /  VPS Deals Wire',26,T['muted']);thumb.save(P/'thumbnail.jpg',quality=94)
def encode(cid):
 P=B/cid;timing=json.loads((P/'timing.json').read_text());record=json.loads((P/'screen-recording.json').read_text());segs=[];total=0
 for r in timing:
  i=r['index'];dur=r['seconds']+.45;out=P/f'segment-{i:02}.mp4';cmd=['ffmpeg','-v','error','-y','-loop','1','-framerate','24','-i',str(P/f'scene-{i:02}.png')]
  if i==2:
   cmd+=['-ss','4' if cid.startswith('td') else '1','-i',record['videoFile'],'-i',str(P/r['wav'])]
   filt='[1:v]crop=1320:760:60:140,scale=1170:674,tpad=stop_mode=clone:stop_duration=30[real];[0:v][real]overlay=80:310,format=yuv420p[v];[2:a]apad=pad_dur=0.5[a]' if cid.startswith('td') else '[1:v]crop=1300:690:65:160,scale=1170:621,tpad=stop_mode=clone:stop_duration=30[real];[0:v][real]overlay=80:320,format=yuv420p[v];[2:a]apad=pad_dur=0.5[a]'
  else:cmd+=['-i',str(P/r['wav'])];filt='[0:v]format=yuv420p[v];[1:a]apad=pad_dur=0.5[a]'
  cmd+=['-filter_complex',filt,'-map','[v]','-map','[a]','-t',str(dur),'-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-threads','2','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(out)];
  if not __import__('os').environ.get('ONLY_SCENES') or str(i) in __import__('os').environ['ONLY_SCENES'].split(','):subprocess.run(cmd,check=True)
  segs.append(out);r.update(videoStart=total,videoEnd=total+dur);total+=dur;print(cid,'scene',i,flush=True)
 (P/'concat.txt').write_text(''.join("file '"+str(x)+"'\n"for x in segs));subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(P/f'{cid}.mp4')],check=True);(P/'video-timing.json').write_text(json.dumps(timing,indent=2)+'\n');print('DONE',cid,(P/f'{cid}.mp4').stat().st_size,flush=True)
if __name__=='__main__':
 import sys
 for cid in sys.argv[1:]:
  td() if cid.startswith('td')else vw();encode(cid)
