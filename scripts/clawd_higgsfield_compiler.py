import subprocess, json, os, sys, numpy as np
RAW="/workspace/web/showcase-2027/assets/higgsfield/raw"; OUT="/workspace/web/showcase-2027/assets/higgsfield"
LIMIT=1.1*1024*1024
def run(c): return subprocess.run(c,capture_output=True,text=True)
def probe(f):
    j=json.loads(run(["ffprobe","-v","error","-select_streams","v:0","-count_frames","-show_entries","stream=nb_read_frames,r_frame_rate,width,height:format=duration","-of","json",f]).stdout)
    s=j["streams"][0]; n,d=map(int,s["r_frame_rate"].split("/"))
    return int(s["nb_read_frames"]), n/d, float(j["format"]["duration"]), s["width"], s["height"]
def frame(f,i,w=320,h=180):
    r=subprocess.run(["ffmpeg","-v","error","-i",f,"-vf",f"select=eq(n\\,{i}),scale={w}:{h}","-vframes","1","-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True)
    return np.frombuffer(r.stdout,np.uint8).reshape(h,w,3)/255.0
def rmse(f,n): a,b=frame(f,0),frame(f,n-1); return float(np.sqrt(((a-b)**2).mean()))
res={}
for fn in sorted(os.listdir(RAW)):
    if not fn.endswith(".mp4"): continue
    src=os.path.join(RAW,fn); base=fn[:-4]
    n,fps,dur,w,h=probe(src); d0=rmse(src,n); work=src; d1=d0; stitched=False
    if d0>0.02:
        X=12/fps; L=dur
        st=f"/tmp/{base}_st.mp4"
        # crossfade tail into head: output = [X..L-X] then xfade(tail, head) of length X -> loop seam is continuous
        fc=(f"[0:v]split=2[a][b];[a]trim=start={X}:end={L},setpts=PTS-STARTPTS,fps={fps},settb=AVTB[main];"
            f"[b]trim=0:{X},setpts=PTS-STARTPTS,fps={fps},settb=AVTB[head];"
            f"[main][head]xfade=transition=fade:duration={X}:offset={L-2*X},format=yuv420p")
        r=run(["ffmpeg","-y","-v","error","-i",src,"-filter_complex",fc,"-an","-c:v","libx264","-crf","12",st])
        if r.returncode==0:
            work=st; stitched=True; n2,_,_,_,_=probe(st); d1=rmse(st,n2)
        else: print("xfade fail",fn,r.stderr[-400:])
    out={}
    for scale in [1080,720,540]:
        vf=f"scale=-2:{scale}" if h>scale else "null"
        mp4=f"{OUT}/{base}.mp4"; webm=f"{OUT}/{base}.webm"
        for crf in ([18,23,28,32] ):
            run(["ffmpeg","-y","-v","error","-i",work,"-vf",vf,"-an","-c:v","libx264","-crf",str(crf),"-preset","slow","-pix_fmt","yuv420p","-movflags","+faststart",mp4])
            mc=crf
            if os.path.getsize(mp4)<=LIMIT: break
        for crf in ([24,32,38,44]):
            run(["ffmpeg","-y","-v","error","-i",work,"-vf",vf,"-an","-c:v","libvpx-vp9","-crf",str(crf),"-b:v","0","-row-mt","1","-deadline","good","-cpu-used","2",webm])
            wc=crf
            if os.path.getsize(webm)<=LIMIT: break
        if os.path.getsize(mp4)<=LIMIT and os.path.getsize(webm)<=LIMIT: break
    out=dict(res=scale,mp4_crf=mc,webm_crf=wc,mp4_kb=os.path.getsize(mp4)//1024,webm_kb=os.path.getsize(webm)//1024)
    run(["ffmpeg","-y","-v","error","-i",f"{OUT}/{base}.mp4","-vframes","1","-vf","scale=-2:720","-q:v","4",f"{OUT}/{base}.jpg"])
    res[fn]=dict(frames=n,fps=round(fps,2),src=f"{w}x{h}",seam_before=round(d0,4),seam_after=round(d1,4),stitched=stitched,**out)
    print(fn,res[fn],flush=True)
json.dump(res,open(f"{OUT}/receipt.json","w"),indent=1)
