from PIL import Image,ImageFont,ImageDraw,ImageChops
from pathlib import Path
import json,hashlib
HERE=Path(__file__).resolve().parent;F=Path('/usr/share/fonts/truetype/dejavu');BG='#F7F4EE';INK='#171717';MUTED='#756F67';LINE='#D9D1C5';ACC='#783F42'
def font(n,b=False,mono=False):return ImageFont.truetype(str(F/(('DejaVuSansMono'if mono else'DejaVuSans')+('-Bold'if b else'')+'.ttf')),n)
def text(d,xy,s,n=28,c=INK,b=False,anchor=None,mono=False):d.text(xy,s,font=font(n,b,mono),fill=c,anchor=anchor)
def panel(d,box,fill):d.rounded_rectangle(box,radius=18,fill=fill,outline=LINE,width=2)
def fit(im,a,box):
 a=a.copy();a.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);pos=(box[0]+(box[2]-box[0]-a.width)//2,box[1]+(box[3]-box[1]-a.height)//2);im.paste(a,pos,a)if a.mode=='RGBA'else im.paste(a,pos)

import argparse
parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);args=parser.parse_args()
# Original authority diagram: no provider UI, live lookup or invented measurement.
im=Image.new('RGB',(1200,630),BG);d=ImageDraw.Draw(im);text(d,(55,34),'VPS DEALS WIRE  /  DNS CHECKLIST',20,ACC,b=True);text(d,(55,89),'Check who controls each direction.',48,b=True)
for y,label,left,right,record in [(185,'FORWARD — YOUR DOMAIN DNS ZONE','node.example.com','203.0.113.10','A'),(370,'REVERSE — IP PROVIDER OR DELEGATED ZONE','203.0.113.10','node.example.com','PTR')]:
 panel(d,(55,y,1145,y+155),'#FFFDF9');text(d,(80,y+18),label,22,ACC,b=True);text(d,(87,y+83),left,29,mono=True);text(d,(1107,y+83),right,29,mono=True,anchor='ra');d.line((527,y+102,650,y+102),fill=INK,width=4);d.polygon([(666,y+102),(649,y+91),(649,y+113)],fill=INK);text(d,(594,y+70),record,25,ACC,b=True,anchor='mm')
text(d,(55,567),'Documentation values only. No DNS query or server change performed.',24,MUTED)
im.save(Path(args.output))
