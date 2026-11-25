"""Build a single-file gift using the convert() function transcribed from the recording.
The source clip supplies frames; missing program settings are supplied explicitly below.
No MP4 is shipped to the browser. Each frame is a sparse array of ASCII cells.
"""
import argparse,base64,importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np

parser=argparse.ArgumentParser();parser.add_argument('video');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('visible',root/'reference/ascii_player.visible.py');module=importlib.util.module_from_spec(spec);module.np=np;module.cv2=cv2;spec.loader.exec_module(module)
ramp=' .,:;irsXA253hMHGS#9B&@'
class Adapter:
    cols=120;rows=185
    s=SimpleNamespace(mode='ascii',color=True,saturation=1.0,edges=0,bg_tint=0)
    lut=np.arange(256,dtype=np.uint8)
    ramp=np.array(list(ramp))
    @staticmethod
    def _pack(rgb):
        a=np.clip(rgb,0,255).astype(np.uint32)
        return (a[...,0]<<16)|(a[...,1]<<8)|a[...,2]
renderer=Adapter();capture=cv2.VideoCapture(args.video);frames=[]
for k in range(207):
    capture.set(cv2.CAP_PROP_POS_MSEC,k*(1000/12))
    ok,frame=capture.read()
    if not ok:break
    crop=frame[100:728,156:564]
    glyph,fg,bg=module.convert(renderer,crop)
    buf=bytearray()
    for index in np.flatnonzero(glyph.ravel()!=' '):
        char=str(glyph.ravel()[index]);c=int(fg.ravel()[index]);r=(c>>16)&255;g=(c>>8)&255;b=c&255
        rgb332=(r&224)|((g&224)>>3)|(b>>6)
        buf.extend((int(index)&255,int(index)>>8,rgb332,ramp.index(char)))
    frames.append(base64.b64encode(buf).decode())
capture.release()
html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#000"><meta name="description" content="A little bouquet, just for you. Happy birthday, sunshine."><title>Happy birthday, sunshine</title><style>
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:#000;color:#f5eacb;font-family:Georgia,serif}main{min-height:100svh;padding:max(12px,env(safe-area-inset-top)) 12px max(22px,env(safe-area-inset-bottom));display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}canvas{display:block;width:min(94vw,420px);height:min(70svh,650px);touch-action:pan-y}h1{font-weight:400;font-size:clamp(24px,6.4vw,30px);line-height:1.18;text-align:center;margin:0}h1 span{display:block;font-style:italic;color:#f1d79d;font-size:1.1em;margin-top:4px}button{min-height:44px;border:1px solid #695e49;border-radius:24px;padding:10px 25px;background:none;color:#bdb19a;font:15px Georgia;touch-action:manipulation;cursor:pointer}button:focus-visible{outline:2px solid #f1d79d;outline-offset:4px}@media(orientation:landscape)and(max-height:530px){main{flex-direction:row;gap:24px}canvas{width:45vw;height:88svh}}
</style></head><body><main><canvas role="img" aria-label="An animated bouquet made of colourful text characters"></canvas><h1>Happy birthday,<span>sunshine</span></h1><button type="button">Начать заново</button></main><script>
const encoded=FRAME_DATA;
const ramp=RAMP_DATA;
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d'),frames=encoded.map(s=>{const b=atob(s),a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a});
const palette=Array.from({length:256},(_,v)=>`rgb(${Math.round((v>>5)*255/7)},${Math.round(((v>>2)&7)*255/7)},${Math.round((v&3)*255/3)})`);
let start=performance.now(),W,H,sx,sy,ox,oy;const reduced=matchMedia('(prefers-reduced-motion:reduce)').matches;
const layers=[document.createElement('canvas'),document.createElement('canvas')],cache=[-1,-1];let dpr=1;
function resize(){const r=canvas.getBoundingClientRect();dpr=Math.min(devicePixelRatio||1,2);W=r.width;H=r.height;canvas.width=Math.round(W*dpr);canvas.height=Math.round(H*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);let scale=Math.min(W/120,H/185);sx=scale;sy=scale;ox=(W-120*sx)/2;oy=(H-185*sy)/2;for(const layer of layers){layer.width=canvas.width;layer.height=canvas.height}cache.fill(-1)}addEventListener('resize',resize);resize();
function paint(slot,frame){if(cache[slot]===frame)return;const c=layers[slot].getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,H);c.font=`${sy*1.25}px 'Courier New',monospace`;c.textBaseline='middle';const f=frames[frame];let previous=-1;for(let i=0;i<f.length;i+=4){const index=f[i]|(f[i+1]<<8),color=f[i+2];if(color!==previous){c.fillStyle=palette[color];previous=color}c.fillText(ramp[f[i+3]],ox+(index%120)*sx,oy+Math.floor(index/120)*sy)}cache[slot]=frame}
function draw(now){requestAnimationFrame(draw);if(document.hidden)return;const position=reduced?132:(Math.max(0,now-start)*12/1000)%frames.length,frame=Math.floor(position),next=(frame+1)%frames.length,t=reduced?0:position-frame,slot=frame%2,other=1-slot;paint(slot,frame);paint(other,next);ctx.clearRect(0,0,W,H);ctx.globalAlpha=1-t;ctx.drawImage(layers[slot],0,0,W,H);ctx.globalCompositeOperation='lighter';ctx.globalAlpha=t;ctx.drawImage(layers[other],0,0,W,H);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over'}requestAnimationFrame(draw);document.querySelector('button').onclick=()=>{start=performance.now();cache.fill(-1)};

</script></body></html>'''
html=html.replace('FRAME_DATA',json.dumps(frames,separators=(',',':'))).replace('RAMP_DATA',json.dumps(ramp))
(root/'dist/index.html').write_text(html,encoding='utf-8')
print(json.dumps({'frames':len(frames),'bytes':len(html.encode()),'external_requests':0}))
