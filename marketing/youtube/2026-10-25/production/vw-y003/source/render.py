from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops,ImageOps
import json,subprocess
B=Path('/workspace/work/youtube-ops-2026-10-25/production');F=Path('/usr/share/fonts/truetype/dejavu')
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
 im=Image.new('RGB',(1920,1080),T['bg']);d=ImageDraw.Draw(im);txt(d,(80,45),T['brand']+'  /  '+('LETTERING NOTES' if T is TD else 'BUYING NOTES'),24,T['accent'],b=True);txt(d,(1840,45),f'{i+1:02} / 07',24,T['muted'],anchor='ra');txt(d,(80,130),title,60,b=True,serif=T is TD);txt(d,(80,223),sub,29,T['muted']);d.line((80,290,1840,290),fill=T['line'],width=2);txt(d,(80,1015),'Digital lettering references; final artwork needs artist review.' if T is TD else 'Conceptual checklist; no latency test performed.',23,T['muted']);txt(d,(1840,1015),T['domain'],25,T['accent'],anchor='ra');return im,d
def save(i,im):im.save(P/f'scene-{i:02}.png')
def cropink(path):
 im=Image.open(path).convert('RGBA');mask=ImageChops.multiply(ImageOps.invert(ImageOps.grayscale(im)),im.getchannel('A')).point(lambda v:255 if v>40 else 0);bb=mask.getbbox();return im.crop((max(0,bb[0]-20),max(0,bb[1]-20),min(im.width,bb[2]+20),min(im.height,bb[3]+20)))
def arrow(d,a,b):d.line((a,b),fill=T['accent'],width=6);x,y=b;d.polygon([(x,y),(x-18,y-12),(x-18,y+12)],fill=T['accent'])

def td_long():
 global T,P
 T=TD;P=B/'td-y002';raw=[Image.open(P/(x+'.png')).convert('RGBA') for x in ['baseline','alternative']];boxes=[]
 for im in raw:
  mask=ImageChops.multiply(ImageOps.invert(ImageOps.grayscale(im)),im.getchannel('A')).point(lambda v:255 if v>40 else 0);boxes.append(mask.getbbox())
 box=(max(0,min(x[0] for x in boxes)-25),max(0,min(x[1] for x in boxes)-25),max(x[2] for x in boxes)+25,max(x[3] for x in boxes)+25);exports=[im.crop(box) for im in raw]
 im,d=base(0,'Same words. Same font. One change.','Compare two genuine lettering exports with only the spacing changed.')
 for j,(label,a) in enumerate(zip(['BASELINE','ALTERNATIVE'],exports)):
  y=345+j*295;panel(d,(80,y,1840,y+257));txt(d,(120,y+30),label,24,T['accent'],b=True);fit(im,a,(380,y+35,1740,y+220))
 save(0,im)
 im,d=base(1,'Make a controlled comparison.','Actual tool recording: keep the phrase and font fixed.')
 panel(d,(1310,335,1840,937));txt(d,(1350,385),'FIXED',26,T['accent'],b=True)
 for j,s in enumerate(['Stay curious','Courier Prime','Same preview size']):para(d,(1350,465+j*115),s,420,32)
 para(d,(1350,824),'Change the spacing control only.',420,28,T['muted']);save(1,im)
 details=[]
 for a in exports:
  mask=ImageChops.multiply(ImageOps.invert(ImageOps.grayscale(a)),a.getchannel('A')).point(lambda v:255 if v>40 else 0);runs=[];start=None
  for x in range(a.width):
   occupied=mask.crop((x,0,x+1,a.height)).getbbox() is not None
   if occupied and start is None:start=x
   if not occupied and start is not None:runs.append((start,x));start=None
  if start is not None:runs.append((start,a.width))
  assert len(runs)==11,(len(runs),runs)
  details.append(a.crop((runs[3][0]-8,0,runs[6][1]+8,a.height)))
 dw=max(a.width for a in details);padded=[]
 for a in details:
  c=Image.new('RGBA',(dw,a.height),(0,0,0,0));c.paste(a,((dw-a.width)//2,0),a);padded.append(c)
 im,d=base(2,'Check the word break as well.','An edit that changes one pair also changes the full phrase.')
 for j,(label,a) in enumerate(zip(['BASELINE','ALTERNATIVE'],padded)):
  y=350+j*290;panel(d,(80,y,1840,y+250));txt(d,(120,y+30),label+' / WORD BREAK',23,T['accent']);fit(im,a,(625,y+30,1515,y+225))
 save(2,im)
 im,d=base(3,'Ask a fresh reader.','Let them read the preview before you tell them the words.')
 panel(d,(80,360,1840,880));fit(im,exports[1],(220,440,1700,680));txt(d,(960,796),'Uncertainty is feedback, not a test result.',32,T['muted'],anchor='mm');save(3,im)
 im,d=base(4,'Show the difference you prefer.','A browser setting is not a physical gap on skin.')
 panel(d,(80,355,1110,925));fit(im,exports[1],(125,445,1065,680));txt(d,(595,810),'A digital direction to discuss',30,T['muted'],anchor='mm');panel(d,(1190,355,1840,925));txt(d,(1230,410),'ASK YOUR ARTIST',25,T['accent'],b=True);para(d,(1230,530),'Can you review this spacing direction in the final lettering?',550,37);para(d,(1230,785),'Final size and artwork need a separate decision.',550,28,T['muted']);save(4,im)
 im,d=base(5,'Keep a plain-text master.','Proofread the export again before saving your preference.')
 panel(d,(80,360,880,920));txt(d,(130,410),'VERIFIED WORDING',25,T['accent']);txt(d,(480,620),'Stay curious',60,serif=True,anchor='mm');panel(d,(960,360,1840,920));txt(d,(1005,410),'RECHECK THE IMAGE',25,T['accent']);fit(im,exports[0],(1000,510,1790,700));txt(d,(1400,813),'Case · spelling · word break',29,T['muted'],anchor='mm');save(5,im)
 im,d=base(6,'Prepare one clear question.','Read the complete letter-spacing comparison guide.')
 panel(d,(80,340,1130,940));fit(im,Image.open(P/'guide.png').convert('RGB'),(100,360,1110,920));txt(d,(1210,430),'THE FULL GUIDE',26,T['accent'],b=True);txt(d,(1210,520),'tattoodoodle.com',43,b=True);para(d,(1210,655),'Direct guide link in the description.',580,34);para(d,(1210,825),'Reference, not a physical-size guarantee.',580,28,T['muted']);save(6,im)
 thumb=Image.new('RGB',(1280,720),T['bg']);d=ImageDraw.Draw(thumb);txt(d,(55,45),'CHANGE ONE THING.',62,b=True,serif=True);txt(d,(55,130),'Compare the spacing.',32,T['muted'])
 for j,a in enumerate(exports):
  y=245+j*190;panel(d,(55,y,1225,y+160));txt(d,(80,y+16),'BASELINE' if j==0 else 'ALTERNATIVE',19,T['accent']);fit(thumb,a,(300,y+25,1165,y+140))
 txt(d,(55,665),'Same words · same font  /  Tattoo Doodle',23,T['muted']);thumb.save(P/'thumbnail.jpg',quality=94)

def vw_long():
 global T,P
 T=VW;P=B/'vw-y002'
 im,d=base(0,'Nearest is a starting point.','A city label does not prove the best connection for your users.')
 for j,(a,b) in enumerate([('USERS','Their real connection'),('VPS REGION','A candidate location'),('DEPENDENCIES','Database, API, delivery layer')]):
  x=80+j*600;panel(d,(x,390,x+550,850));txt(d,(x+35,440),a,27,T['accent'],b=True);para(d,(x+35,590),b,480,37)
  if j<2:arrow(d,(x+558,620),(x+590,620))
 txt(d,(960,932),'Conceptual path. No measured latency values.',29,T['muted'],anchor='mm');save(0,im)
 im,d=base(1,'Start with where users connect.','The person paying the invoice may be far from the audience.')
 panel(d,(80,370,1180,920));txt(d,(630,475),'AUDIENCE NETWORK',36,T['accent'],b=True,anchor='mm')
 for x,label in [(330,'Users'),(850,'Candidate VPS')]:d.ellipse((x-92,575,x+92,759),fill=T['line']);txt(d,(x,810),label,31,anchor='mm')
 arrow(d,(455,665),(725,665));panel(d,(1260,370,1840,920));para(d,(1300,465),'Choose a connection representative of the people using the service.',490,37);para(d,(1300,790),'Not simply the billing address.',490,28,T['muted']);save(1,im)
 im,d=base(2,'Find the permitted test method.','Actual guide recording; no provider test was executed for this video.')
 panel(d,(1320,335,1840,935));txt(d,(1360,390),'VERIFY FIRST',26,T['accent'],b=True)
 for j,s in enumerate(['Provider test facility','Allowed use','Representative network']):para(d,(1360,490+j*132),s,430,32)
 save(2,im)
 im,d=base(3,'Leave untested observations blank.','A template is a plan, never proof of a measurement.')
 panel(d,(80,350,1840,930))
 for j,(k,v) in enumerate([('Region','Candidate region'),('Time / network','Record when testing'),('Method','Confirm permitted method'),('Result','NOT RUN')]):
  y=400+j*122;txt(d,(125,y),k.upper(),25,T['accent'],b=True);txt(d,(650,y),v,35);d.line((125,y+86,1795,y+86),fill=T['line'],width=2)
 save(3,im)
 im,d=base(4,'Look at where dependencies live.','Repeated trips to a distant database can change the application path.')
 for j,(a,b) in enumerate([('USER','Requests the service'),('APPLICATION','Runs in a VPS region'),('DATABASE','A separate dependency')]):
  x=80+j*600;panel(d,(x,390,x+550,850));txt(d,(x+35,445),a,29,T['accent'],b=True);para(d,(x+35,570),b,460,37)
  if j<2:arrow(d,(x+558,620),(x+590,620))
 txt(d,(960,932),'Diagram explains a question to test; it does not predict a response time.',28,T['muted'],anchor='mm');save(4,im)
 im,d=base(5,'Shortlist, then make a test plan.','Compare the route and the application, rather than a city name alone.')
 for j,(a,b) in enumerate([('CANDIDATE A','Check region and policy'),('CANDIDATE B','Use the same method')]):
  x=80+j*900;panel(d,(x,375,x+860,920));txt(d,(x+40,430),a,30,T['accent'],b=True);para(d,(x+40,560),b,740,42);para(d,(x+40,790),'No winner until you have relevant evidence.',740,29,T['muted'])
 save(5,im)
 im,d=base(6,'Read the location checklist.','Verify the candidate region with the provider before committing.')
 panel(d,(80,340,1130,940));fit(im,Image.open(P/'guide.png').convert('RGB'),(100,360,1110,920));txt(d,(1210,425),'THE FULL GUIDE',26,T['accent'],b=True);txt(d,(1210,520),'vpsdealswire.com',43,b=True);para(d,(1210,665),'Direct checklist link in the description.',580,34);para(d,(1210,825),'No lowest-latency winner is claimed.',580,28,T['muted']);save(6,im)
 thumb=Image.new('RGB',(1280,720),T['bg']);d=ImageDraw.Draw(thumb);txt(d,(55,42),'VPS DEALS WIRE',23,T['accent'],b=True);txt(d,(55,155),'CLOSEST',91,b=True);txt(d,(55,265),'IS A HYPOTHESIS.',66,b=True);panel(d,(55,420,1225,615))
 for j,s in enumerate(['Users','Region','Dependencies']):txt(d,(105+j*380,492),s,30,T['accent'],b=True)
 txt(d,(55,656),'Plan a relevant test before choosing.',29,T['muted']);thumb.save(P/'thumbnail.jpg',quality=94)

def portrait_base(title,sub):
 im=Image.new('RGB',(1080,1920),T['bg']);d=ImageDraw.Draw(im);txt(d,(70,155),T['brand'],28,T['accent'],b=True);para(d,(70,260),title,940,67);para(d,(70,465),sub,940,31,T['muted']);txt(d,(70,1660),T['domain'],32,T['accent']);return im,d

def shorts():
 global T,P
 T=TD;P=B/'td-y003';S=Path('/workspace/tattoo-generator/marketing/youtube/2026-10-25/source');arts=[cropink(S/f'{s}.png') for s in ['great-vibes','cinzel','courier-prime']]
 im,d=portrait_base('Same words. Three directions.','Actual lettering exports: Stay curious')
 for j,(a,label) in enumerate(zip(arts,['Great Vibes  /  Script','Cinzel  /  Serif','Courier Prime  /  Typewriter'])):
  y=615+j*280;panel(d,(70,y,1010,y+240));fit(im,a,(110,y+28,970,y+155));txt(d,(540,y+194),label,27,T['muted'],anchor='mm')
 save(0,im)
 im,d=portrait_base('Keep the wording fixed.','One preference. One useful alternative.')
 for j,(a,label) in enumerate([(arts[2],'A PREFERENCE'),(arts[1],'AN ALTERNATIVE')]):
  y=665+j*365;panel(d,(70,y,1010,y+310));txt(d,(110,y+32),label,25,T['accent']);fit(im,a,(115,y+95,965,y+255))
 save(1,im)
 im,d=portrait_base('Find the full comparison.','On this channel: Same Words, Three Tattoo Fonts')
 panel(d,(70,665,1010,1190));fit(im,arts[2],(115,790,965,1000));para(d,(110,1070),'Website link in the full video description.',840,31);para(d,(85,1340),'A digital reference, not a finished tattoo.',900,39);save(2,im)
 thumb=Image.open(P/'scene-00.png');thumb.thumbnail((720,1280));thumb.save(P/'thumbnail.jpg',quality=94)
 T=VW;P=B/'vw-y003';im,d=portrait_base('More vCPUs? Check the policy.','A plan-fit question, not a benchmark score.')
 for j,(a,b) in enumerate([('ALLOCATION','Shared or dedicated?'),('USAGE','Continuous-use conditions'),('LIMIT RESPONSE','What happens if it stays busy?')]):
  y=645+j*290;panel(d,(70,y,1010,y+245));txt(d,(110,y+38),a,29,T['accent'],b=True);para(d,(110,y+115),b,840,39)
 save(0,im)
 im,d=portrait_base('Match the workload.','Do not treat a CPU count as a usage promise.')
 panel(d,(70,675,1010,1370));txt(d,(110,730),'CONTINUOUS TASK',31,T['accent'],b=True)
 for j in range(10):d.rounded_rectangle((120+j*83,900,167+j*83,1120),radius=8,fill='#F5CE74')
 para(d,(110,1220),'Conceptual illustration. No measurement.',840,32,T['muted']);save(1,im)
 im,d=portrait_base('Watch the full checklist.','On this channel: Shared vCPU VPS')
 panel(d,(70,685,1010,1215));txt(d,(110,765),'FAIR USE BEFORE BUYING',37,T['accent'],b=True);para(d,(110,910),'The full video description links to the complete guide.',840,43);para(d,(85,1375),'Confirm actual terms with the provider.',900,38);save(2,im)
 thumb=Image.open(P/'scene-00.png');thumb.thumbnail((720,1280));thumb.save(P/'thumbnail.jpg',quality=94)

def encode(cid):
 P=B/cid;timing=json.loads((P/'timing.json').read_text());is_short=cid.endswith('003');segs=[];total=0
 if is_short:
  dur=timing[0]['seconds']+.55
  for i,frac in enumerate([.43,.30,.27]):
   out=P/f'segment-{i:02}.mp4';seconds=dur*frac;subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',str(P/f'scene-{i:02}.png'),'-t',str(seconds),'-vf','format=yuv420p','-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-threads','2','-an',str(out)],check=True);segs.append(out)
  (P/'concat.txt').write_text(''.join("file '"+str(x)+"'\n" for x in segs));subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-i',str(P/timing[0]['wav']),'-map','0:v','-map','1:a','-c:v','copy','-af','apad=pad_dur=0.6,loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-t',str(dur),'-movflags','+faststart',str(P/f'{cid}.mp4')],check=True)
  timing[0].update(videoStart=0,videoEnd=dur)
 else:
  raw=json.loads((P/'screen-recording.json').read_text())['videoFile']
  for r in timing:
   i=r['index'];dur=r['seconds']+.45;out=P/f'segment-{i:02}.mp4';cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',str(P/f'scene-{i:02}.png')]
   if i==(1 if cid.startswith('td') else 2):
    cmd+=['-ss','1','-i',raw,'-i',str(P/r['wav'])];filt=('[1:v]crop=1320:760:60:140,scale=1170:674,tpad=stop_mode=clone:stop_duration=30[real];[0:v][real]overlay=80:310,format=yuv420p[v];[2:a]apad=pad_dur=0.5[a]' if cid.startswith('td') else '[1:v]crop=1300:690:65:160,scale=1170:621,tpad=stop_mode=clone:stop_duration=30[real];[0:v][real]overlay=80:320,format=yuv420p[v];[2:a]apad=pad_dur=0.5[a]')
   else:cmd+=['-i',str(P/r['wav'])];filt='[0:v]format=yuv420p[v];[1:a]apad=pad_dur=0.5[a]'
   cmd+=['-filter_complex',filt,'-map','[v]','-map','[a]','-t',str(dur),'-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-threads','2','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(out)];
   if not __import__('os').environ.get('OPS_ONLY_SCENES') or str(i) in __import__('os').environ['OPS_ONLY_SCENES'].split(','):subprocess.run(cmd,check=True)
   r.update(videoStart=total,videoEnd=total+dur);total+=dur;segs.append(out);print(cid,'scene',i,flush=True)
  (P/'concat.txt').write_text(''.join("file '"+str(x)+"'\n" for x in segs));subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','112k','-ar','48000','-ac','2','-movflags','+faststart',str(P/f'{cid}.mp4')],check=True)
 (P/'video-timing.json').write_text(json.dumps(timing,indent=2)+'\n');print('DONE',cid,(P/f'{cid}.mp4').stat().st_size,flush=True)

if __name__=='__main__':
 import sys
 target=sys.argv[1:]
 if not target:target=['td-y002','td-y003','vw-y002','vw-y003']
 if 'td-y002'in target:td_long()
 if 'vw-y002'in target:vw_long()
 if any(x.endswith('003') for x in target):shorts()
 for cid in target:encode(cid)
