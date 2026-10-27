from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps,ImageChops
import argparse
HERE=Path(__file__).resolve().parent
F=Path('/usr/share/fonts/truetype/dejavu')
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
def f(n,b=False,serif=False):return ImageFont.truetype(str(F/(('DejaVuSerif'if serif else'DejaVuSans')+('-Bold'if b else'')+'.ttf')),n)
def txt(d,xy,s,n,c,b=False,serif=False):d.text(xy,s,font=f(n,b,serif),fill=c)
def fit(im,a,box):
 a=a.copy();a.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);xy=(box[0]+(box[2]-box[0]-a.width)//2,box[1]+(box[3]-box[1]-a.height)//2);im.paste(a,xy,a if a.mode=='RGBA'else None)
im=Image.new('RGB',(1200,630),'#101D2B');d=ImageDraw.Draw(im);txt(d,(45,30),'VPS / MEMORY NOTES',18,'#65D9C4',True);txt(d,(45,87),'Swap used is only one observation.',45,'#F4F7F8',True)
for j,(label,lines)in enumerate([('AVAILABLE RAM',['Estimated room','for applications']),('ACTIVE SWAP',['Separate backing','area, not extra RAM']),('WORKLOAD EVIDENCE',['Same time period','as the symptom'])]):
 x=45+j*380;d.rounded_rectangle((x,220,x+350,490),radius=15,fill='#192B3D',outline='#355063',width=2);txt(d,(x+22,250),label,20,'#65D9C4',True)
 for k,s in enumerate(lines):txt(d,(x+22,335+k*40),s,25,'#F4F7F8')
txt(d,(45,550),'Definitions and questions, not measured memory or benchmark output.',25,'#ACBDCB');txt(d,(45,594),'vpsdealswire.com',18,'#65D9C4');im.save(args.output)
