from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,hashlib
B=Path(__file__).resolve().parent;F=Path('/usr/share/fonts/truetype/dejavu')
im=Image.open(B/'tattoo-hero.png');p=B/'tattoo/content/seo-queue/assets/uppercase-lowercase-tattoo-lettering.webp';im.save(p,quality=92);im.resize((375,211)).save(B/'tattoo-mobile.png')
im=Image.new('RGB',(1200,630),'#101D2B');d=ImageDraw.Draw(im)
def t(s,x,y,n=25,c='#F4F7F8',bold=False):d.text((x,y),s,font=ImageFont.truetype(str(F/('DejaVuSans-Bold.ttf'if bold else'DejaVuSans.ttf')),n),fill=c)
t('VPS / NETWORK PATHS',40,30,18,'#65D9C4',True);t('IPv6-only: check both directions.',40,78,42,bold=True)
rows=[('IPv4-only visitor','IPv6-only origin','Needs a supported bridge'),('IPv6-capable visitor','IPv6-only origin','Check route, firewall and service'),('IPv6-only server','IPv4-only dependency','Needs a supported outbound path')]
for j,(a,b,c)in enumerate(rows):
 y=190+j*110;d.rounded_rectangle((40,y,1160,y+92),radius=12,fill='#192B3D');t(a,60,y+18,23);t('to',435,y+18,22,'#ACBDCB');t(b,510,y+18,23);t(c,60,y+55,22,'#65D9C4')
t('Conceptual paths only. No connection test or provider guarantee.',40,552,24,'#ACBDCB');t('vpsdealswire.com',40,598,17,'#65D9C4');p=B/'vps/static/articles/ipv6-only-vps-connectivity-checklist.png';im.save(p);im.save(B/'vps-hero.png');im.resize((375,197)).save(B/'vps-mobile.png');p=B/'vps/content/calendar.json';q=json.loads(p.read_text());q['entries'][-1]['image_sha256']=hashlib.sha256((B/'vps/static/articles/ipv6-only-vps-connectivity-checklist.png').read_bytes()).hexdigest();p.write_text(json.dumps(q,indent=2)+'\n')
