#!/usr/bin/env python3
from pathlib import Path
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    raise SystemExit("Pillow is required: python3 -m pip install pillow")

ROOT = Path(__file__).resolve().parents[1] / "pwa"

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def centered(draw, text, y, fnt, fill, spacing=0):
    box = draw.textbbox((0,0), text, font=fnt)
    w = box[2]-box[0]
    draw.text(((1024-w)/2,y), text, font=fnt, fill=fill)

def make_master():
    n=1024
    img=Image.new("RGB",(n,n),(8,13,19))
    px=img.load()
    for y in range(n):
        for x in range(n):
            dx=(x-n*.36)/n; dy=(y-n*.20)/n
            glow=max(0,1-(dx*dx+dy*dy)*3.2)
            base=int(11+17*(1-y/n))
            px[x,y]=(base+int(10*glow),base+int(18*glow),base+int(25*glow))
    # subtle inner glass panel
    panel=Image.new("RGBA",(n,n),(0,0,0,0))
    pd=ImageDraw.Draw(panel)
    pd.rounded_rectangle((42,42,982,982),radius=190,fill=(8,14,21,135),outline=(185,210,231,75),width=3)
    highlight=Image.new("RGBA",(n,n),(0,0,0,0))
    hd=ImageDraw.Draw(highlight)
    hd.ellipse((85,-230,900,430),fill=(255,255,255,24))
    highlight=highlight.filter(ImageFilter.GaussianBlur(75))
    img=Image.alpha_composite(img.convert("RGBA"),panel)
    img=Image.alpha_composite(img,highlight)
    d=ImageDraw.Draw(img)
    # linked-ring Agency symbol
    ring=(222,232,240,245)
    d.ellipse((280,205,540,465),outline=ring,width=24)
    d.ellipse((484,205,744,465),outline=ring,width=24)
    d.arc((280,205,540,465),200,340,fill=(255,255,255,255),width=7)
    d.arc((484,205,744,465),20,160,fill=(255,255,255,255),width=7)
    # product name first
    centered(d,"AGENCY",545,font(102,True),(244,247,249,255))
    centered(d,"K&C",695,font(48,True),(180,193,204,230))
    # tiny brand line
    centered(d,"AI  •  PEOPLE  •  RESULTS",785,font(24,False),(128,145,159,215))
    return img.convert("RGB")

master=make_master()
for size in (180,192,512):
    out=master.resize((size,size),Image.Resampling.LANCZOS)
    out.save(ROOT/f"icon-{size}.png",optimize=True)
print("K&C Agency icons generated:", ROOT)
