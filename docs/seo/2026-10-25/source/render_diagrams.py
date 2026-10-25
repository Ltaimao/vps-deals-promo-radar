from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,math,hashlib
BASE=Path('/workspace/work/seo15')
FONTS=Path('/usr/share/fonts/truetype/dejavu')
INK='#171717';PAPER='#F7F4EE';MUTED='#746D64';ACCENT='#A4815A';LINE='#DAD2C6'
def font(size,serif=False,bold=False):
 return ImageFont.truetype(str(FONTS/('DejaVuSerif'+('-Bold' if bold else '')+'.ttf' if serif else 'DejaVuSans'+('-Bold' if bold else '')+'.ttf')),size)
def text(d,xy,s,size=24,fill=INK,serif=False,bold=False,anchor=None):
 d.text(xy,s,font=font(size,serif,bold),fill=fill,anchor=anchor)
def wrap(d,s,width,size=24):
 lines=[];line=''
 for w in s.split():
  test=(line+' '+w).strip()
  if d.textlength(test,font=font(size))>width and line:lines.append(line);line=w
  else:line=test
 if line:lines.append(line)
 return lines
def para(d,xy,s,width=300,size=24):
 x,y=xy
 for line in wrap(d,s,width,size):text(d,(x,y),line,size);y+=size*1.45
def panel(d,box):d.rounded_rectangle(box,radius=16,fill='#FFFDFA',outline=LINE,width=2)
def arrow(d,x,y,xx,yy):
 d.line((x,y,xx,yy),fill=ACCENT,width=4);d.polygon([(xx,yy),(xx-12,yy-8),(xx-12,yy+8)],fill=ACCENT)
def base(title,site,h):
 im=Image.new('RGB',(1200,h),PAPER);d=ImageDraw.Draw(im)
 text(d,(64,40),site.upper()+'  /  PLANNING NOTES',19,MUTED)
 text(d,(64,92),title,43,serif=True)
 d.line((64,170,1136,170),fill=LINE,width=2)
 text(d,(64,h-48),'Original conceptual diagram  •  No measured results or physical-size claim',17,MUTED)
 return im,d
def tattoo(item):
 slug=item['slug'];a,b,c,e=item['diagram'];im,d=base(a,'TattooDoodle',675)
 if 'accents' in slug:
  for x,word,label in [(64,'José','Accent retained'),(622,'Jose','Different text')]:
   panel(d,(x,217,x+514,526));text(d,(x+257,290),word,88,serif=True,anchor='mm');text(d,(x+257,450),label,25,MUTED,anchor='mm')
 elif 'line-break' in slug:
  for x in (64,622):panel(d,(x,217,x+514,526))
  text(d,(321,335),'Stay curious',49,serif=True,anchor='mm');text(d,(879,294),'Stay',49,serif=True,anchor='mm');text(d,(879,366),'curious',49,serif=True,anchor='mm')
  text(d,(321,472),'One line',24,MUTED,anchor='mm');text(d,(879,472),'Two lines',24,MUTED,anchor='mm')
 elif 'monogram' in slug:
  for x in (64,622):panel(d,(x,217,x+514,526))
  text(d,(321,330),'A  M',100,serif=True,anchor='mm');text(d,(860,315),'A',120,serif=True,anchor='mm');text(d,(903,349),'M',120,serif=True,anchor='mm',fill=ACCENT)
  text(d,(321,472),'Separate letters',24,MUTED,anchor='mm');text(d,(879,472),'Overlap to discuss',24,MUTED,anchor='mm')
 elif 'punctuation' in slug:
  for x,word,label in [(64,"we're",'Apostrophe included'),(622,'were','Different wording')]:
   panel(d,(x,217,x+514,526));text(d,(x+257,327),word,76,serif=True,anchor='mm');text(d,(x+257,472),label,24,MUTED,anchor='mm')
 elif 'negative-space' in slug:
  for cx,filled in [(321,False),(879,True)]:
   panel(d,(cx-257,217,cx+257,526))
   for side in (-1,1):
    for j in range(3):
     x=cx+side*(75+j*15);y=280+j*48;d.ellipse((x-20,y-33,x+20,y+33),outline=INK,width=4)
    d.arc((cx-105,251,cx+105,444),0 if side==1 else 90,90 if side==1 else 270,fill=INK,width=4)
   if filled:d.ellipse((cx-32,300,cx+32,364),fill=ACCENT)
   else:d.ellipse((cx-32,300,cx+32,364),outline=ACCENT,width=3)
   text(d,(cx,477),'Center added' if filled else 'Center left open',24,MUTED,anchor='mm')
 elif 'matching' in slug:
  for i,(name,shapes) in enumerate([('Identical',('o','o')),('Complementary',('o','s')),('Connected',('l','r'))]):
   x=64+i*366;panel(d,(x,217,x+340,526))
   for j,shape in enumerate(shapes):
    cx=x+95+j*150;box=(cx-39,299,cx+39,377)
    if shape=='o':d.ellipse(box,outline=INK,width=5)
    elif shape=='s':d.rectangle(box,outline=INK,width=5)
    else:d.arc(box,90 if shape=='l' else -90,270 if shape=='l' else 90,fill=INK,width=5)
   text(d,(x+170,477),name,23,MUTED,anchor='mm')
 elif 'preview-photo' in slug:
  for i,(name,pts) in enumerate([('Consistent frame',[(150,259),(464,259),(464,429),(150,429)]),('Changed angle',[(738,268),(1052,230),(1090,412),(776,450)])]):
   x=64+i*558;panel(d,(x,217,x+514,526));d.polygon(pts,outline=INK,width=3)
   for p,q in [(pts[0],pts[2]),(pts[1],pts[3])]:d.line((*p,*q),fill=LINE,width=2)
   text(d,(x+257,477),name,23,MUTED,anchor='mm')
  text(d,(600,568),'Abstract camera frames, not a product interface or a body-size model',20,MUTED,anchor='mm')
 elif 'moodboard' in slug:
  for i,(name,icon) in enumerate([('Subject','leaf'),('Composition','layout'),('Texture','shade')]):
   x=64+i*366;panel(d,(x,217,x+340,526));cx=x+170
   if icon=='leaf':d.ellipse((cx-32,280,cx+32,395),outline=INK,width=4);d.line((cx,288,cx,420),fill=INK,width=3)
   elif icon=='layout':
    for j in range(3):d.rectangle((cx-78+j*52,295+j*15,cx-47+j*52,387+j*15),outline=INK,width=3)
   else:
    for j in range(8):d.line((cx-65+j*18,290,cx-65+j*18,410),fill=INK,width=1+j%3)
   text(d,(cx,477),name,23,MUTED,anchor='mm')
 else:
  labels=[b,c,e]
  for i,label in enumerate(labels):
   x=64+i*366;panel(d,(x,217,x+340,526));cx=x+170
   d.rounded_rectangle((cx-58,264,cx+58,398),radius=5,outline=INK,width=3)
   for j,w in enumerate((72,58,80)):d.line((cx-39,299+j*24,cx-39+w,299+j*24),fill=ACCENT if i==2 else LINE,width=4)
   para(d,(x+26,445),label,288,22)
   if i<2:arrow(d,x+344,335,x+362,335)
 text(d,(64,580),'Concepts for discussion with an artist; final artwork requires separate review.',20,MUTED)
 im.save(OUTPUT_DIR/(slug+'.webp'),'WEBP',quality=91)
 return im
def vps(item):
 slug=item['slug'];a,*labels=item['diagram'];im,d=base(a,'VPS Deals Wire',630)
 for i,label in enumerate(labels):
  x=64+i*366;panel(d,(x,211,x+340,518));cx=x+170
  text(d,(x+24,232),'0'+str(i+1),22,ACCENT,bold=True)
  if 'snapshot' in slug:
   d.rounded_rectangle((cx-65,291,cx+65,386),radius=8,outline=INK,width=4)
   for j in range(3):d.line((cx-43,315+j*22,cx+43,315+j*22),fill=LINE,width=4)
   if i==1:d.line((cx-10,346,cx+4,360,cx+31,326),fill=ACCENT,width=5)
  elif 'dns' in slug:
   if i==0:
    text(d,(cx,329),'A + AAAA',32,bold=True,anchor='mm')
   elif i==1:
    d.ellipse((cx-45,283,cx+45,373),outline=INK,width=4);d.line((cx,298,cx,329,cx+24,340),fill=ACCENT,width=4)
   else:
    d.arc((cx-46,286,cx+46,378),20,310,fill=INK,width=4);d.polygon([(cx-42,292),(cx-17,293),(cx-37,313)],fill=ACCENT)
  else:
   d.rectangle((cx-46,279,cx+46,387),outline=INK,width=3)
   for j in range(3):d.line((cx-28,307+j*23,cx+28,307+j*23),fill=ACCENT if j==i else LINE,width=4)
  para(d,(x+25,428),label,290,24)
  if i<2:arrow(d,x+344,336,x+362,336)
 im.save(OUTPUT_DIR/(slug+'.png'),optimize=True)
 return im

if __name__ == '__main__':
 import argparse
 parser=argparse.ArgumentParser(description='Offline original editorial diagrams; never called by publication workflows.')
 parser.add_argument('--site',choices=('tattoo','vps'),required=True)
 parser.add_argument('--briefs',type=Path,default=Path(__file__).with_name('visual-briefs.json'))
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();OUTPUT_DIR=args.output;OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
 for item in json.loads(args.briefs.read_text()):
  (tattoo if args.site=='tattoo' else vps)(item)
 print('Rendered reviewed input briefs; re-review image changes before updating publication checksums.')
