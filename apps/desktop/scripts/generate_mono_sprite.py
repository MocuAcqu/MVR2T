"""Generate Mono's pixel sprite (apps/desktop/src/components/mono/sprite.ts).

Mono is MVR2T's original mascot: a round white "mochi" rabbit with long ears (light-gray inside), no mouth
(the nose is the expressive part), and paws/feet that only appear while it is doing something.

The sprite is drawn from simple shapes (ellipses, a bezier "tube" for the floppy ears) and every part gets an
automatic 1-pixel black outline. Parts are layered by src/components/mono/compose.ts.

Usage (standard library only):
    python scripts/generate_mono_sprite.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "components" / "mono" / "sprite.ts"

N=32; H=36
def ell(cx,cy,rx,ry,ang=0,p=2.0):
    a=math.radians(ang); ca,sa=math.cos(a),math.sin(a)
    def f(x,y):
        dx,dy=x+.5-cx,y+.5-cy
        u=dx*ca+dy*sa; v=-dx*sa+dy*ca
        return abs(u/rx)**p+abs(v/ry)**p<=1
    return f
def blobf(cx=16.0,cy=23.2,a=11.0,bt=11.0,bb=10.0):
    def f(x,y):
        dx,dy=x+.5-cx,y+.5-cy
        if dy<0: return abs(dx/a)**2.2+abs(dy/bt)**2.2<=1
        return abs(dx/a)**3.4+abs(dy/bb)**3.4<=1   # flatter bottom: sits on the ground
    return f
def layer(fill, inner=None, shade=None, color='W', ic='G', sc='L', clip=None):
    F={(x,y) for x in range(N) for y in range(H) if fill(x,y) and (clip is None or clip(x,y))}
    out={}
    for (x,y) in F:
        c=color
        if shade and not shade(x,y): c=sc
        if inner and inner(x,y): c=ic
        out[(x,y)]=c
    for (x,y) in F:
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            p=(x+dx,y+dy)
            if p not in F and 0<=p[0]<N and 0<=p[1]<H: out[p]='K'
    return out
def merge(*ds):
    o={}
    for d in ds: o.update(d)
    return o
def part(d):
    if not d: return None
    xs=[p[0] for p in d]; ys=[p[1] for p in d]; x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
    g=[['.']*(x1-x0+1) for _ in range(y1-y0+1)]
    for (x,y),c in d.items(): g[y-y0][x-x0]=c
    return {"at":[x0,y0],"rows":[''.join(r) for r in g]}
def pts(lst,c='K'): return {(x,y):c for x,y in lst}
def bez(p0,p1,p2,n=40):
    return [((1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t*t*p2[0],(1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t*t*p2[1]) for t in [i/n for i in range(n+1)]]
def tube(path,r0,r1):
    def f(x,y):
        X,Y=x+.5,y+.5
        for i,(px,py) in enumerate(path):
            r=r0+(r1-r0)*i/(len(path)-1)
            if (X-px)**2+(Y-py)**2<=r*r: return True
        return False
    return f
def lop(p0,p1,p2):
    path=bez(p0,p1,p2)
    return layer(tube(path,1.8,2.4), inner=tube(path[9:-3],0.6,1.2))
def ear(cx,cy,rx,ry,a):
    return layer(ell(cx,cy,rx,ry,a), inner=ell(cx,cy+0.5,rx-1.25,ry-1.7,a))
P={"size":N,"height":H,"palette":{"K":"#000000","D":"#4b4b4b","G":"#afafaf","L":"#e2e2e2","W":"#ffffff"}}
P["blob"]=part(layer(blobf(), shade=blobf(15.0,22.0)))
P["feet"]=part(merge(layer(ell(11.5,33.7,2.3,1.25),shade=ell(11.1,33.2,2.3,1.25)),layer(ell(20.5,33.7,2.3,1.25),shade=ell(20.1,33.2,2.3,1.25))))
def tail(dx=0,dy=0): return part(layer(ell(27.5+dx,29.6+dy,2.6,2.4), shade=ell(27.0+dx,29.1+dy,2.6,2.4)))
P["tail"]={"rest":tail(),"up":tail(0,-1),"wag":tail(1,0)}
EY=7.6
P["ears"]={
 "up":   {"back":part(merge(ear(11.8,EY,2.5,6.3,-8),ear(20.2,EY,2.5,6.3,8)))},
 "tilt": {"back":part(merge(ear(12.9,EY+.3,2.5,6.3,14),ear(21.4,EY+.8,2.5,6.3,28)))},
 "sway": {"back":part(merge(ear(10.6,EY+.8,2.5,6.3,-28),ear(19.1,EY+.3,2.5,6.3,-14)))},
 "fold": {"back":part(merge(ear(11.8,EY,2.5,6.3,-8),ear(20.7,EY+2.6,2.4,3.8,6))),
          "front":part(ear(24.3,EY+2.6,2.0,4.0,128))},
 "down": {"front":part(merge(lop((9.9,13.8),(3.1,10.6),(3.4,25.0)),lop((22.1,13.8),(28.9,10.6),(28.6,25.0))))},
}
EYE=20
def eyepair(f): return part(merge(f(9),f(21)))
P["eyes"]={
 "open": eyepair(lambda x: pts([(x+i,EYE+1+j) for i in range(2) for j in range(2)])),
 "blink":eyepair(lambda x: pts([(x-1,EYE+2),(x,EYE+2),(x+1,EYE+2),(x+2,EYE+2)])),
 "happy":eyepair(lambda x: pts([(x-1,EYE+2),(x,EYE+1),(x+1,EYE+1),(x+2,EYE+2)])),
 "sleep":eyepair(lambda x: pts([(x-1,EYE+1),(x,EYE+2),(x+1,EYE+2),(x+2,EYE+1)])),
 "wide": eyepair(lambda x: pts([(x+i,EYE+j) for i in range(2) for j in range(3)])),
 "down": eyepair(lambda x: pts([(x+i,EYE+1+j) for i in range(2) for j in range(2)])),
 "look": eyepair(lambda x: pts([(x+1+i,EYE+1+j) for i in range(2) for j in range(2)])),
 "x":    eyepair(lambda x: pts([(x-1,EYE),(x+2,EYE),(x,EYE+1),(x+1,EYE+1),(x-1,EYE+2),(x+2,EYE+2)])),
}
P["cheeks"]=part(pts([(6,EYE+3),(7,EYE+3),(24,EYE+3),(25,EYE+3)],'L'))
NY=EYE+3
P["nose"]={
 "dot":  part(pts([(15,NY),(16,NY)],'D')),
 "up":   part(pts([(15,NY-1),(16,NY-1)],'D')),                     # wiggle frame
 "sniff":part(pts([(15,NY),(16,NY),(15,NY+1),(16,NY+1)],'D')),      # bigger, sniffing
 "tiny": part(pts([(15,NY+1)],'D')),                                # sad / small
}
def paw(cx,cy,rx=1.5,ry=1.15): return layer(ell(cx,cy,rx,ry), shade=ell(cx-.4,cy-.4,rx,ry))
P["shadow"]=part({(x,34):"L" for x in range(7,25)})
P["hands"]={"none":None,
 "rest": part(merge(paw(5.5,27.6,1.6,1.3),paw(26.5,27.6,1.6,1.3))),
 "wave": part(merge(paw(5.5,27.6,1.6,1.3),paw(26.7,20.6,1.7,1.4))),
 "cheer":part(merge(paw(5.9,21.0,1.7,1.4),paw(26.1,21.0,1.7,1.4))),
 "cover":part(merge(paw(10.5,21.4,1.8,1.4),paw(21.5,21.4,1.8,1.4))),   # paws over eyes (shy / error)
 "hold": part(merge(paw(8.6,29.6),paw(23.4,29.6))),
}
def headphones():
    band=layer(lambda x,y: ell(16.0,23.2,12.0,12.0)(x,y) and not ell(16.0,23.2,10.9,10.9)(x,y) and y<=18, color='D')
    cups={}
    for cx in (4.5,27.5): cups.update(layer(ell(cx,21.8,1.7,2.9), color='D', inner=ell(cx,21.8,.7,1.7), ic='G'))
    return part(merge(band,cups))
def note(x,y): return pts([(x+2,y),(x+3,y),(x+2,y+1),(x+2,y+2),(x+1,y+3),(x+2,y+3),(x,y+4),(x+1,y+4)])
def tablet(frame):
    d={}
    x0,y0,w,h=9,25,14,9
    for x in range(x0,x0+w):
        for y in range(y0,y0+h):
            d[(x,y)]='K' if (x in (x0,x0+w-1) or y in (y0,y0+h-1)) else 'D'
    # flicker line first, then a big, clear play triangle on top of it
    band = 26 if frame==1 else 32
    for x in range(x0+1,x0+w-1): d[(x,band)]='G'
    for p in [(14,y) for y in range(27,33)]+[(15,y) for y in range(28,32)]+[(16,29),(16,30)]: d[p]='W'
    return part(d)
P["props"]={"headphones":headphones(),"notes1":part(merge(note(0,7),note(27,9))),"notes2":part(merge(note(0,5),note(27,7))),
            "tablet1":tablet(1),"tablet2":tablet(2)}


def main() -> None:
    body = json.dumps(P, ensure_ascii=False, indent=1)
    OUT.write_text(
        "// GENERATED by scripts/generate_mono_sprite.py. Do not edit by hand; change the script and re-run it.\n"
        "import type { MonoSprite } from './types';\n\n"
        f"export const MONO_SPRITE: MonoSprite = {body};\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
