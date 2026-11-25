'use strict';
const video=document.querySelector('video'),button=document.querySelector('button'),canvas=document.querySelector('#universe'),ctx=canvas.getContext('2d'),box=document.querySelector('.flowers');
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
let W,H,D,phase='flowers',started=0,last=0,seed=19,shot=null,origin=null,points=[],stars=[];
const clamp=v=>Math.min(1,Math.max(0,v));const smooth=v=>{v=clamp(v);return v*v*v*(v*(v*6-15)+10)};
function random(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296}
function gauss(){return Math.sqrt(-2*Math.log(Math.max(.00001,random())))*Math.cos(6.283185*random())}
function hsv(h,v=1){h=(h%1+1)%1;const f=n=>{let k=(n+h*12)%12;return Math.round(255*v*(1-.7*Math.max(-1,Math.min(k-3,9-k,1))))};return [f(0),f(8),f(4)]}
function resize(){W=innerWidth;H=innerHeight;D=Math.min(devicePixelRatio||1,2);canvas.width=W*D;canvas.height=H*D;ctx.setTransform(D,0,0,D,0,0)}addEventListener('resize',resize);resize();
// Values transcribed from the supplied Turtle program: 780x480, TILT=.45,
// 140 stars, 700 dust dots, arms(900) with four arms, 260 core dots, 40 sparkles.
function place(x,y){y*=.55;return [x*Math.cos(.45)-y*Math.sin(.45),-(x*Math.sin(.45)+y*Math.cos(.45))]}
function build(){seed=19;points=[];stars=[];for(let i=0;i<140;i++)stars.push({x:random(),y:random(),r:1+Math.floor(random()*3)});
 const add=(x,y,c,size)=>{let [px,py]=place(x,y);points.push({x:px,y:py,c,size})};
 for(let i=0;i<700;i++){let r=gauss()*120,a=random()*6.283185;add(r*Math.cos(a),r*Math.sin(a),hsv(.7,.3),2+Math.floor(random()*3))}
 for(let i=0;i<900;i++)for(let k=0;k<4;k++){let d=i/900,a=k*Math.PI/2+d*5.5,r=10+d*290,s=4+d*26;add(r*Math.cos(a)+gauss()*s,r*Math.sin(a)+gauss()*s,hsv(.13-d*.55,.6+random()*.4),2+Math.floor(random()*3))}
 for(let i=0;i<260;i++){let r=gauss()*26,a=random()*6.283185;add(r*Math.cos(a),r*Math.sin(a),hsv(.12),2+Math.floor(random()*4))}
 for(let i=0;i<40;i++){let r=gauss()*150,a=random()*6.283185;add(r*Math.cos(a),r*Math.sin(a),[255,255,255],5+Math.floor(random()*4))}
 add(0,0,[255,243,196],26);
}
function begin(){if(phase!=='flowers')return;shot=document.createElement('canvas');shot.width=408;shot.height=728;shot.getContext('2d').drawImage(video,156,0,408,728,0,0,408,728);origin=box.getBoundingClientRect();video.pause();build();
 let data=shot.getContext('2d').getImageData(0,0,408,728).data,samples=[];
 // Sample the selected flower rather than scattering the entire bouquet.
 for(let y=220;y<460;y+=2)for(let x=90;x<300;x+=2){let i=(y*408+x)*4;if(Math.max(data[i],data[i+1],data[i+2])>32)samples.push({x:x/408,y:y/728,c:[data[i],data[i+1],data[i+2]]})}
 for(let i=0;i<points.length;i++){let s=samples.length?samples[i%samples.length]:{x:.5,y:.46,c:[230,190,220]};points[i].source=s;points[i].delay=random()*.10;points[i].arc=(random()-.5)*2}
 phase='journey';started=performance.now();document.body.classList.add('travel')}
video.muted=true;video.loop=true;video.addEventListener('timeupdate',()=>{if(video.currentTime>=11.5)begin()});video.play().catch(()=>button.textContent='Play your gift');
button.onclick=()=>{phase='flowers';document.body.classList.remove('travel');points=[];shot=null;video.currentTime=0;video.play().catch(()=>{});button.textContent='Watch again'};
function draw(now){requestAnimationFrame(draw);if(now-last<30)return;last=now;ctx.clearRect(0,0,W,H);if(phase==='flowers')return;
 let seconds=(now-started)/1000,zoom=smooth(seconds/4.8),dissolve=smooth((seconds-3.8)/7.2);if(reduced){zoom=1;dissolve=smooth(seconds/1.2)}
 let r=box.getBoundingClientRect(),centerX=W/2,centerY=r.top+r.height*.5,scale=Math.min(W/780*.96,r.height/480*.92,1.3),magnify=1+zoom*4.5;
 // A continuous camera push into the upper central flower, followed by a seven-second dissolve.
 let fx=.48,fy=.45,imgW=origin.width*magnify,imgH=origin.height*magnify;
 let anchorX=origin.left+origin.width*fx+(centerX-origin.left-origin.width*fx)*zoom,anchorY=origin.top+origin.height*fy+(centerY-origin.top-origin.height*fy)*zoom;
 let left=anchorX-imgW*fx,top=anchorY-imgH*fy;
 ctx.globalAlpha=1-dissolve;ctx.filter=`brightness(1.35) blur(${dissolve*7}px)`;ctx.drawImage(shot,left,top,imgW,imgH);ctx.filter='none';ctx.globalAlpha=1;
 let starAlpha=smooth((seconds-4)/6);ctx.fillStyle='#fff';for(let s of stars){ctx.globalAlpha=starAlpha*.7;ctx.beginPath();ctx.arc(s.x*W,s.y*H,Math.max(.45,s.r*scale*.5),0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;
 if(dissolve<=0)return;
 for(let q of points){let t=smooth((dissolve-q.delay)/(1-q.delay)),s=q.source,sx=left+s.x*imgW,sy=top+s.y*imgH,tx=centerX+q.x*scale,ty=centerY+q.y*scale;let arc=Math.sin(t*Math.PI)*q.arc*35;let x=sx+(tx-sx)*t+arc,y=sy+(ty-sy)*t+arc*.3;let c=s.c.map((v,i)=>Math.round(v+(q.c[i]-v)*t));ctx.fillStyle=`rgba(${c.join(',')},${dissolve})`;ctx.beginPath();ctx.arc(x,y,Math.max(.35,q.size*scale*.5),0,Math.PI*2);ctx.fill()}
}requestAnimationFrame(draw);
