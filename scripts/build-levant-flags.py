#!/usr/bin/env python3
"""Draw an original faction atlas; never copies the EA chrome image."""
import re
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]

def banner(name,w,h):
 im=Image.new('RGBA',(w,h),(35,43,40));d=ImageDraw.Draw(im)
 stripes={'france':['#244b9b','white','#bd3842'],'germany':['#171d20','#b72b31','#dbc050'],'russia':['white','#315b9a','#bb3a44'],'iran':['#39814f','white','#c54843'],'yemen':['#c44543','white','#202426'],'saudi':['#237546'],'china':['#c43831'],'turkey':['#c43831'],'ukraine':['#3e67a5','#ddc451'],'israel':['white','#44729d','white']}
 if name=='israel':
  d.rectangle((0,0,w,h),fill='#edece3');d.rectangle((0,h*.13,w,h*.25),fill='#44729d');d.rectangle((0,h*.75,w,h*.87),fill='#44729d')
  d.polygon([(w/2,h*.30),(w*.39,h*.65),(w*.61,h*.65)],outline='#44729d');d.polygon([(w/2,h*.70),(w*.39,h*.35),(w*.61,h*.35)],outline='#44729d')
 elif name=='hezbollah':
  d.rectangle((0,0,w,h),fill='#555c3d');d.rectangle((0,h-3,w,h),fill='#b3b881');d.ellipse((w*.38,h*.18,w*.62,h*.77),outline='#e0dbaf',width=1)
 elif name in ('england','america'):
  if name=='england':
   d.rectangle((0,0,w,h),fill='#f0eee7');d.rectangle((w*.4,0,w*.6,h),fill='#b73a3e');d.rectangle((0,h*.37,w,h*.63),fill='#b73a3e')
  else:
   for y in range(7):d.rectangle((0,y*h/7,w,(y+1)*h/7),fill='#bb4748' if y%2==0 else '#edece4')
   d.rectangle((0,0,w*.46,h*.58),fill='#355780')
 elif name in stripes:
  colors=stripes[name]
  for i,color in enumerate(colors):
   if name in ('france','germany') and name=='france':d.rectangle((i*w/len(colors),0,(i+1)*w/len(colors),h),fill=color)
   else:d.rectangle((0,i*h/len(colors),w,(i+1)*h/len(colors)),fill=color)
  if name=='turkey':d.ellipse((w*.34,h*.20,w*.65,h*.79),fill='#edece4');d.ellipse((w*.42,h*.20,w*.72,h*.79),fill='#c43831')
  if name=='china':d.regular_polygon((w*.25,h*.35,h*.18),5,rotation=0,fill='#ebd066')
 else:
  d.rectangle((0,0,w,h),fill='#537689' if 'allies' in name.lower() else '#98674d' if 'soviet' in name.lower() else '#4c6157')
  d.text((2,1),name[:2].upper() if not name.startswith('Random') else '?',font=ImageFont.load_default(),fill='#e9ecd8')
 return im

for mode,folder in [('ra2',ROOT/'RTSAI-Mod/mods/rtsai'),('ra',ROOT/'OpenRA/mods/ra')]:
 path=folder/'chrome.yaml';text=path.read_text(encoding='utf-8');m=re.search(r'^flags:\n(.*?)(?=^\S|\Z)',text,re.S|re.M);block=m[0]
 if '\t\tisrael:' not in block:block=block.rstrip()+'\n\t\tisrael: 260, 1, 30, 15\n\t\thezbollah: 260, 17, 30, 15\n\n'
 rects=re.findall(r'^\t\t([^:]+): (\d+), (\d+), (\d+), (\d+)\s*$',block,re.M)
 atlas=Image.new('RGBA',(512,384))
 for name,x,y,w,h in rects:atlas.alpha_composite(banner(name,int(w),int(h)),(int(x),int(y)))
 asset=folder/'uibits/faction-flags.png' if mode=='ra' else folder/'modern-factions/ui/faction-flags.png';asset.parent.mkdir(exist_ok=True);atlas.save(asset)
 reference='faction-flags.png' if mode=='ra' else 'ra2|modern-factions/ui/faction-flags.png'
 block=re.sub(r'^\tImage:.*$',f'\tImage: {reference}',block,flags=re.M)
 block=re.sub(r'^\tImage[23]x:.*\n','',block,flags=re.M)
 for scale in (2,3):
  scaled=asset.with_name(asset.stem+f'-{scale}x.png');atlas.resize((atlas.width*scale,atlas.height*scale),Image.Resampling.NEAREST).save(scaled)
  block=block.replace(f'\tImage: {reference}\n',f'\tImage: {reference}\n\tImage{scale}x: {reference.removesuffix(".png")}-{scale}x.png\n')
 text=text[:m.start()]+block+text[m.end():];path.write_text(text,encoding='utf-8',newline='\n')
 print(mode+': original procedural flag atlas')
