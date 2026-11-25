/* Procedural lily surfaces, projected through a depth buffer into coloured ASCII. */
'use strict';
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
let seed=17;function random(){seed=(1664525*seed+1013904223)>>>0;return seed/4294967296}
const pts=[],stars=[];const palette=[];
function color(rgb,light){const c=rgb.map(v=>Math.max(0,Math.min(255,Math.round(v*light/12)*12)));const key=c.join(',');let i=palette.indexOf(key);if(i<0){i=palette.length;palette.push(key)}return i}
function point(x,y,z,rgb,light,stage,glyph){pts.push({x,y,z,c:color(rgb,light),stage,glyph})}
const green=[92,195,58];
// Rear flowers first; the depth buffer resolves overlapping petals, stems and stamens.
const flowers=[
 {x:-65,y:-103,z:-48,r:55,c:[245,226,196],rx:-.30,ry:-.48,a:.13},
 {x:65,y:-125,z:-50,r:56,c:[232,200,39],rx:.38,ry:.65,a:.3},
 {x:5,y:-166,z:-65,r:45,c:[235,179,133],rx:-.45,ry:.35,a:.15},
 {x:-78,y:-4,z:-35,r:53,c:[244,197,35],rx:.5,ry:-.8,a:.05},
 {x:83,y:-25,z:-30,r:58,c:[161,37,77],rx:-.35,ry:.62,a:.25},
 {x:78,y:132,z:-22,r:48,c:[175,36,44],rx:.45,ry:.9,a:.35},
 {x:-67,y:117,z:-5,r:47,c:[242,208,38],rx:-.4,ry:-.7,a:.2},
 {x:0,y:-96,z:44,r:76,c:[225,30,43],rx:.14,ry:-.22,a:-.15},
 {x:-42,y:17,z:54,r:76,c:[226,117,204],rx:-.25,ry:-.15,a:.24},
 {x:44,y:66,z:75,r:80,c:[243,231,200],rx:.35,ry:.22,a:-.12},
 {x:0,y:132,z:91,r:68,c:[240,197,151],rx:-.2,ry:-.35,a:.2}
];
function rotate(x,y,z,f){let a=y*Math.cos(f.rx)-z*Math.sin(f.rx),b=y*Math.sin(f.rx)+z*Math.cos(f.rx);return [x*Math.cos(f.ry)+b*Math.sin(f.ry),a,b*Math.cos(f.ry)-x*Math.sin(f.ry)]}
for(const f of flowers){
 for(let j=0;j<450;j++){let t=j/450;for(let w=-1;w<=1;w++)point(f.x*(1-t)+Math.sin(t*3)*6+w*.8,f.y*(1-t)+228*t,f.z*(1-t)-30,green,.55+random()*.35,(1-t)*.2,'|')}
 for(let k=0;k<6;k++){
  const a=k*Math.PI/3+f.a;
  for(let row=0;row<75;row++)for(let col=0;col<39;col++){
   let t=(row+.5)/75,v=(col-19)/19;
   let length=f.r*(k%2?1:.92),w=length*.31*Math.pow(Math.sin(Math.PI*t),.85)*(1-.2*t);
   // Petals rise from a deep throat, arch out, then curl backwards at the pointed tip.
   let radial=length*(t+.13*Math.sin(Math.PI*t));
   let x=radial*Math.cos(a)-v*w*Math.sin(a),y=radial*Math.sin(a)+v*w*Math.cos(a);
   let z=length*(.68*Math.sin(t*Math.PI*.9)-.52*t*t)+v*v*length*.13;
   let q=rotate(x,y,z,f);
   let edge=Math.abs(v),vein=Math.cos(v*24+t*10)*.035;
   let light=.38+.48*Math.sin(t*2.1)+edge*.17+vein+random()*.1;
   if(t<.29)light*=.6+t;
   let speck=(t<.6&&random()<.06)? .40:1;
   point(f.x+q[0],f.y+q[1],f.z+q[2],f.c,light*speck,.24+(180-f.y)/1400,'-');
  }
 }
 for(let k=0;k<6;k++){let a=k*Math.PI/3+.4;for(let j=0;j<65;j++){let t=j/64,q=rotate(Math.cos(a)*t*19,Math.sin(a)*t*17-6*t,8+t*37,f);point(f.x+q[0],f.y+q[1],f.z+q[2],[182,167,84],.8,.37+(180-f.y)/1400,'.')}
 let q=rotate(Math.cos(a)*19,Math.sin(a)*17-6,45,f);for(let j=0;j<45;j++)point(f.x+q[0]+(random()-.5)*7,f.y+q[1]+(random()-.5)*3,f.z+q[2],[143,87,41],.8+random()*.3,.4+(180-f.y)/1400,'=')}
}
for(let k=0;k<24;k++){let side=k%2?1:-1,bottom=130+random()*95,len=45+random()*65;for(let j=0;j<400;j++){let t=random(),v=random()*2-1;point(side*len*t,bottom-38*Math.sin(t*Math.PI)-12*t+v*Math.sin(t*Math.PI)*5,-25+v*3,green,.38+random()*.45,.05+t*.2,'-')}}
for(let i=0;i<160;i++)stars.push([random(),random(),random()]);
let W,H,D,cols,rows,depth,cell,started=performance.now(),last=0;
function resize(){const r=canvas.getBoundingClientRect();W=r.width;H=r.height;D=Math.min(devicePixelRatio||1,2);canvas.width=W*D;canvas.height=H*D;ctx.setTransform(D,0,0,D,0,0);cols=210;cell=W/cols;rows=Math.ceil(H/cell/1.3);depth=new Float32Array(cols*rows)}
addEventListener('resize',resize);resize();
function draw(now){if(now-last<65){requestAnimationFrame(draw);return}last=now;let progress=reduced?1:Math.min(1,(now-started)/3200);ctx.clearRect(0,0,W,H);depth.fill(-Infinity);const pixels=new Int32Array(cols*rows);pixels.fill(-1);let scale=Math.min(W/325,H/490)*.94,angle=reduced?0:Math.sin(now*.00032)*.16,ca=Math.cos(angle),sa=Math.sin(angle);
for(const p of pts){let grow=reduced?1:Math.min(1,Math.max(0,(progress-p.stage)*4.2));if(!grow)continue;let x=p.x*ca+p.z*sa,z=p.z*ca-p.x*sa,y=228+(p.y-228)*grow;let px=Math.round((W*.5+x*scale)/cell),py=Math.round((H*.49+y*scale)/(cell*1.3));if(px<0||px>=cols||py<0||py>=rows)continue;let i=py*cols+px;if(z>depth[i]){depth[i]=z;pixels[i]=p.c}}
ctx.fillStyle='#9a9584';for(const [x,y,b] of stars){ctx.globalAlpha=.18+b*.4;ctx.fillRect(x*W,y*H,b>.8?1:.65,.65)}ctx.globalAlpha=1;ctx.font=`${cell*1.6}px 'Courier New',monospace`;ctx.textBaseline='middle';
for(let c=0;c<palette.length;c++){ctx.fillStyle=`rgb(${palette[c]})`;for(let i=0;i<pixels.length;i++)if(pixels[i]===c){let x=i%cols,y=(i/cols)|0;ctx.fillText((x+y)%7===0?'=':(x+y)%3===0?':':'-',x*cell,y*cell*1.3)}}
if(!reduced||progress<1)requestAnimationFrame(draw)}requestAnimationFrame(draw);
document.querySelector('#replay').onclick=()=>{started=performance.now();if(reduced)requestAnimationFrame(draw)};
