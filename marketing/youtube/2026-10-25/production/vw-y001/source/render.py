from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,subprocess
P=Path('/workspace/work/youtube-production/vw-y001');F=Path('/usr/share/fonts/truetype/dejavu');BG='#101D2B';PANEL='#192B3D';INK='#F4F7F8';MUTED='#ACBDCB';MINT='#65D9C4';YELLOW='#F5CE74';LINE='#355063'
def font(n,b=False):return ImageFont.truetype(str(F/('DejaVuSans'+('-Bold' if b else '')+'.ttf')),n)
def text(d,xy,s,n=32,color=INK,b=False,anchor=None):d.text(xy,s,font=font(n,b),fill=color,anchor=anchor)
def para(d,xy,s,width,n=30,color=MUTED):
 x,y=xy;l=''
 for w in s.split():
  a=(l+' '+w).strip()
  if d.textlength(a,font=font(n))>width and l:text(d,(x,y),l,n,color);y+=n*1.45;l=w
  else:l=a
 if l:text(d,(x,y),l,n,color)
def panel(d,box,fill=PANEL):d.rounded_rectangle(box,radius=24,fill=fill,outline=LINE,width=2)
def base(i,title,sub):
 im=Image.new('RGB',(1920,1080),BG);d=ImageDraw.Draw(im);text(d,(80,48),'VPS DEALS WIRE  /  BUYING NOTES',24,MINT,b=True);text(d,(1840,48),f'{i+1:02} / 07',24,MUTED,anchor='ra');text(d,(80,130),title,60,b=True);text(d,(80,224),sub,29,MUTED);d.line((80,293,1840,293),fill=LINE,width=2);text(d,(80,1017),'Purchasing checklist. No benchmark performed.',24,MUTED);text(d,(1840,1017),'vpsdealswire.com',25,MINT,anchor='ra');return im,d
def save(i,im):im.save(P/f'scene-{i:02}.png')
def arrow(d,a,b):
 d.line((a,b),fill=MINT,width=6);x,y=b;d.polygon([(x,y),(x-16,y-11),(x-16,y+11)],fill=MINT)
def fit(im,img,box):
 img=img.copy();img.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);im.paste(img,(box[0]+(box[2]-box[0]-img.width)//2,box[1]+(box[3]-box[1]-img.height)//2))

im,d=base(0,'The vCPU count is only the start.','Check the resource policy before comparing headline numbers.')
panel(d,(80,355,660,917));text(d,(370,465),'4 vCPU',78,MINT,b=True,anchor='mm');text(d,(370,555),'EXAMPLE PLAN LABEL',24,MUTED,anchor='mm');para(d,(130,700),'A virtual CPU count does not state a sustained-use allowance.',470,31)
arrow(d,(700,625),(836,625));panel(d,(880,355,1840,917));text(d,(930,410),'THREE QUESTIONS',27,YELLOW,b=True)
for j,(a,b) in enumerate([('Allocation','Shared or dedicated?'),('Limits','What does sustained use allow?'),('Response','What happens at the limit?')]):
 y=500+j*127;text(d,(940,y),a,36,b=True);text(d,(1260,y+4),b,29,MUTED)
text(d,(930,860),'Conceptual example, not a provider offer.',23,MUTED);save(0,im)

im,d=base(1,'Start with the workload.','Occasional bursts and continuously busy tasks ask different questions.')
for x,label,kind in [(80,'SMALL WEBSITE','Bursts between quiet periods'),(976,'CONTINUOUS TASK','Busy over an extended period')]:
 panel(d,(x,355,x+864,920));text(d,(x+38,399),label,30,MINT,b=True);text(d,(x+38,460),kind,28,MUTED)
 for j in range(12):
  high=(j in [2,3,8]) if x==80 else True;h=140 if high else 38;xx=x+52+j*63;d.rounded_rectangle((xx,760-h,xx+40,760),radius=7,fill=YELLOW if high else LINE)
 text(d,(x+38,833),'Illustration only — no measured CPU data.',25,MUTED)
save(1,im)

im,d=base(2,'Read the actual conditions.','The guide turns vague labels into specific questions for support.')
panel(d,(1310,350,1840,928));text(d,(1350,400),'LOOK FOR',28,MINT,b=True)
for j,(a,b) in enumerate([('Sustained use','Threshold or rolling window'),('Burst rules','Credits or duration'),('Limit response','Throttle, warning, suspension')]):
 y=495+j*136;text(d,(1350,y),a,32,b=True);para(d,(1350,y+52),b,440,26)
text(d,(90,944),'Actual public guide • captured 25 Oct 2026',23,MUTED);save(2,im)

im,d=base(3,'A label is not a performance result.','Treat allocation, quantity and your application outcome separately.')
for j,(title,body) in enumerate([('ALLOCATION','Shared / dedicated'),('QUANTITY','Advertised vCPUs'),('YOUR APPLICATION','Response time / completion')]):
 x=80+j*595;panel(d,(x,375,x+565,870));text(d,(x+34,427),title,25,MINT,b=True);para(d,(x+34,565),body,495,40,INK)
text(d,(960,935),'No single label proves the application outcome.',32,YELLOW,anchor='mm');save(3,im)

im,d=base(4,'Keep one small comparison sheet.','Example: a periodic build worker. Record unknowns before paying.')
panel(d,(80,350,1840,930));cols=[(120,'PLAN',300),(455,'POLICY SOURCE',490),(1000,'WORKLOAD',360),(1420,'OPEN QUESTION',370)]
for x,t,w in cols:text(d,(x,398),t,24,MINT,b=True)
d.line((120,464,1800,464),fill=LINE,width=2)
for x,s,w in [(120,'Candidate A',270),(455,'Official product terms + acceptable-use policy',470),(1000,'Periodic build worker',350),(1420,'Is my duty cycle allowed?',350)]:para(d,(x,530),s,w,34,INK)
text(d,(120,822),'Template only. No provider rating, quoted allowance or price.',28,YELLOW);save(4,im)

im,d=base(5,'This is a checklist, not a benchmark.','Before purchase: verify policy. After purchase: observe your actual application.')
for x,a,b in [(80,'CHECK THE TERMS','Confirm which workloads and tests are permitted.'),(980,'TEST YOUR OWN TASK','Use representative work and keep timestamps.')]:
 panel(d,(x,375,x+860,905));text(d,(x+40,430),a,31,MINT,b=True);para(d,(x+40,555),b,740,39,INK)
text(d,(960,950),'No stress test, provider ranking or guaranteed result is shown.',29,YELLOW,anchor='mm');save(5,im)

im,d=base(6,'Make a shortlist. Verify the terms.','Read the fair-use guide, then open the provider’s official policy.')
panel(d,(80,340,1115,930));fit(im,Image.open(P/'guide-top.png').convert('RGB').crop((180,90,1260,930)),(100,360,1095,910));text(d,(1200,420),'THE FULL GUIDE',27,MINT,b=True);text(d,(1200,510),'vpsdealswire.com',43,b=True);para(d,(1200,625),'Direct fair-use guide link in the description.',610,35,INK);para(d,(1200,815),'Confirm current terms with the provider before purchasing.',600,29)
save(6,im)

im=Image.new('RGB',(1280,720),BG);d=ImageDraw.Draw(im);text(d,(55,42),'VPS DEALS WIRE',22,MINT,b=True);text(d,(55,145),'4 vCPU',99,MINT,b=True);text(d,(55,290),'WHAT DOES',66,b=True);text(d,(55,375),'SHARED MEAN?',66,b=True);panel(d,(835,130,1225,615));text(d,(1030,205),'CHECK',39,YELLOW,b=True,anchor='mm')
for j,s in enumerate(['Allocation','Usage limits','Limit response']):text(d,(875,300+j*95),s,29,INK)
text(d,(55,642),'Read the policy before buying.',30,MUTED);im.save(P/'thumbnail.jpg',quality=94)

timing=json.loads((P/'timing.json').read_text());raw=json.loads((P/'screen-recording.json').read_text())['videoFile'];segments=[];total=0
for r in timing:
 i=r['index'];duration=r['seconds']+.45;out=P/f'segment-{i:02}.mp4';cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',str(P/f'scene-{i:02}.png')]
 if i==2:
  cmd+=['-ss','1','-i',raw,'-i',str(P/r['wav'])];filt='[1:v]crop=1300:690:65:160,scale=1170:621,tpad=stop_mode=clone:stop_duration=30[real];[0:v][real]overlay=80:320,format=yuv420p[v];[2:a]apad=pad_dur=0.5[a]'
 else:cmd+=['-i',str(P/r['wav'])];filt='[0:v]format=yuv420p[v];[1:a]apad=pad_dur=0.5[a]'
 cmd+=['-filter_complex',filt,'-map','[v]','-map','[a]','-t',str(duration),'-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-threads','2','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(out)];subprocess.run(cmd,check=True);segments.append(out);r.update(videoStart=total,videoEnd=total+duration);total+=duration;print('Scene',i,round(duration,2),flush=True)
(P/'concat.txt').write_text(''.join("file '"+str(x)+"'\n" for x in segments));subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(P/'vw-y001.mp4')],check=True);(P/'video-timing.json').write_text(json.dumps(timing,indent=2)+'\n');print('Final',round(total,2),(P/'vw-y001.mp4').stat().st_size)
