#!/usr/bin/env python3
"""Verilator GUI: file browser + text editor + run + pop-up waveform.
Usage: python3 vgui.py [folder]   then open http://127.0.0.1:8000
Only built-in Python modules are used. The server listens on 127.0.0.1 only."""
import glob, http.server, secrets, json, os, re, shutil, subprocess, sys, tempfile
from urllib.parse import urlparse, parse_qs

HOME = os.path.realpath(os.path.expanduser('~'))
START = os.path.realpath(sys.argv[1]) if len(sys.argv) > 1 else HOME
HOST = os.environ.get('VGUI_HOST', '127.0.0.1')   # the Docker image sets 0.0.0.0
PORT = int(os.environ.get('VGUI_PORT', '8000'))
TOKEN = os.environ.get('VGUI_TOKEN') or secrets.token_urlsafe(16)   # the launcher passes its own
SRC = ('.v', '.sv', '.vh', '.svh')
WRITE_OK = SRC + ('.txt', '.md', '.do', '.tcl')

PAGE = r'''<!doctype html><meta charset=utf-8><title>Verilator GUI</title>
<style>
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;flex-direction:column;font:14px sans-serif;background:#14202e;color:#e6edf3}
button,input{font:inherit;padding:4px 10px;margin:0 2px}
#top{display:flex;gap:6px;align-items:center;padding:6px 10px;background:#0b1320;flex-wrap:wrap}
#badge{padding:3px 12px;border-radius:12px;font-weight:bold;background:#3a4656}
#badge.green{background:#1f9d55}#badge.red{background:#c0392b}
#main{flex:1;display:flex;min-height:0}
#side{width:260px;border-right:1px solid #2a3a4d;display:flex;flex-direction:column}
#pathbox{width:100%;margin:0;border-radius:0}
#list{flex:1;overflow:auto}
.it{padding:3px 10px;cursor:pointer;white-space:nowrap}.it:hover{background:#1d2f44}.it.cur{background:#24405f}.it.dir{color:#7fd1d1}
#center{flex:1;display:flex;flex-direction:column;min-width:0}
#tabs{display:flex;background:#0b1320;overflow-x:auto;min-height:32px}
.tab{padding:6px 12px;cursor:pointer;border-right:1px solid #2a3a4d;white-space:nowrap}.tab.on{background:#0f1b2a;border-top:2px solid #0e8c8c}
.tab b{margin-left:8px;color:#9fb3c8}
#ed{flex:1;display:flex;min-height:0;background:#0f1b2a}
#gut{width:50px;overflow:hidden;text-align:right;padding:8px 6px 8px 0;color:#6b7c93;font:13px/19.5px monospace;white-space:pre;user-select:none;background:#0b1320}
#gut .e{color:#ff6b6b;font-weight:bold}
#ta{flex:1;border:0;outline:0;resize:none;background:#0f1b2a;color:#e6edf3;font:13px/19.5px monospace;padding:8px;white-space:pre;overflow:auto;tab-size:4}
#bot{height:200px;border-top:1px solid #2a3a4d;display:flex;flex-direction:column}
#bt{display:flex;background:#0b1320}
#bt span{padding:5px 14px;cursor:pointer}#bt span.on{border-bottom:2px solid #0e8c8c}
#out,#probs{flex:1;margin:0;padding:8px;overflow:auto;font:12px monospace;white-space:pre-wrap}
.prob{padding:2px 0;cursor:pointer}.prob:hover{background:#1d2f44}.sev-Error{color:#ff6b6b}.sev-Warning{color:#f5c542}
#win{position:fixed;left:6%;top:7%;width:86%;height:70%;background:#0b1320;border:1px solid #4b5b70;box-shadow:0 8px 30px #000a;resize:both;overflow:hidden;display:flex;flex-direction:column;z-index:10}
#win[hidden]{display:none}
#bar{cursor:move;padding:6px 10px;background:#24405f;display:flex;justify-content:space-between;align-items:center}
#wrap{flex:1;overflow:auto}
</style>
<div id=top>
 <button id=run>Run</button><button id=save>Save</button><button id=newf>New file</button>
 Top module: <input id=topm size=18> <span id=badge>Ready</span>
 <button id=wave disabled>Show waveform</button>
</div>
<div id=main>
 <div id=side><input id=pathbox><div id=list></div></div>
 <div id=center>
  <div id=tabs></div>
  <div id=ed><div id=gut></div><textarea id=ta wrap=off spellcheck=false placeholder="Open a file from the browser, or click New file"></textarea></div>
  <div id=bot><div id=bt><span id=tout class=on>Output</span><span id=tprob>Problems (0)</span></div>
   <pre id=out></pre><div id=probs style="display:none"></div></div>
 </div>
</div>
<div id=win hidden>
 <div id=bar><b>Waveform</b><span><span id=ctl></span> <button id=zi>+</button><button id=zo>-</button><button id=fit>Fit</button><button id=exp>Export PNG</button><button id=wx>Close</button></span></div>
 <div id=wrap><canvas id=cv width=300 height=10></canvas></div>
</div>
<script>
const $=id=>document.getElementById(id);
const TOKEN=new URLSearchParams(location.search).get('t')||'';
const api=async(p,body)=>{
  const o=body?{method:'POST',headers:{'X-VGUI':TOKEN,'Content-Type':'application/json'},body:JSON.stringify(body)}:{headers:{'X-VGUI':TOKEN}};
  const r=await fetch(p,o);const j=await r.json();if(j.error)throw new Error(j.error);return j;};
let cwd='',files={},cur=null,errs=[],sigs=[],tmax=0,scale=1,unit='',ct=null,lock=false;

// ---------- file browser ----------
async function ls(path){
  try{
    const j=await api('/api/ls?path='+encodeURIComponent(path||''));
    cwd=j.path;$('pathbox').value=cwd;
    const L=$('list');L.innerHTML='';
    const add=(txt,cls,fn)=>{const d=document.createElement('div');d.className='it '+cls;d.textContent=txt;d.onclick=fn;L.appendChild(d);return d;};
    if(j.parent)add('.. (up)','dir',()=>ls(j.parent));
    j.entries.forEach(e=>{
      if(e.dir)add(e.name+'/','dir',()=>ls(cwd+'/'+e.name));
      else{const d=add(e.name,e.name===(cur&&cur.split('/').pop())&&cur.startsWith(cwd)?'cur':'',()=>openFile(cwd+'/'+e.name));}
    });
    const tops=j.modules||[];
    if(tops.length&&!tops.includes($('topm').value))$('topm').value=tops.find(m=>/^tb/i.test(m))||tops[tops.length-1];
  }catch(e){alert(e.message);}
}
$('pathbox').onkeydown=e=>{if(e.key==='Enter')ls($('pathbox').value);};

// ---------- editor ----------
async function openFile(p){
  try{
    if(!files[p]){const j=await api('/api/read?path='+encodeURIComponent(p));files[p]={text:j.text,dirty:false};}
    cur=p;tabs();show();ls(cwd);
  }catch(e){alert(e.message);}
}
function tabs(){
  const T=$('tabs');T.innerHTML='';
  Object.keys(files).forEach(p=>{
    const d=document.createElement('div');d.className='tab'+(p===cur?' on':'');
    d.textContent=p.split('/').pop()+(files[p].dirty?' *':'');
    const x=document.createElement('b');x.textContent='x';
    x.onclick=ev=>{ev.stopPropagation();closeTab(p);};d.appendChild(x);
    d.onclick=()=>{cur=p;tabs();show();};T.appendChild(d);
  });
}
function closeTab(p){
  if(files[p].dirty&&!confirm('Discard unsaved changes to '+p.split('/').pop()+'?'))return;
  delete files[p];
  if(cur===p)cur=Object.keys(files)[0]||null;
  tabs();show();
}
function show(){$('ta').value=cur?files[cur].text:'';$('ta').disabled=!cur;gutter();}
function errLines(){
  const s=new Set();
  if(cur)errs.forEach(e=>{if(cwd+'/'+e.file===cur&&e.sev==='Error')s.add(e.line);});
  return s;
}
function gutter(){
  const n=($('ta').value.match(/\n/g)||[]).length+1,bad=errLines();let h='';
  for(let i=1;i<=n;i++)h+=bad.has(i)?'<span class=e>'+i+'</span>\n':i+'\n';
  $('gut').innerHTML=h;$('gut').scrollTop=$('ta').scrollTop;
}
$('ta').oninput=()=>{if(!cur)return;files[cur].text=$('ta').value;files[cur].dirty=true;tabs();gutter();};
$('ta').onscroll=()=>{$('gut').scrollTop=$('ta').scrollTop;};
$('ta').onkeydown=e=>{
  if(e.key==='Tab'){e.preventDefault();const t=e.target;t.setRangeText('    ',t.selectionStart,t.selectionEnd,'end');t.oninput();}
  if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();saveAll();}
};
async function saveAll(){
  for(const p of Object.keys(files))if(files[p].dirty){await api('/api/write',{path:p,text:files[p].text});files[p].dirty=false;}
  tabs();
}
$('save').onclick=saveAll;
$('newf').onclick=async()=>{
  const n=prompt('New file name (for example adder.v)');if(!n)return;
  if(/[\/\\]/.test(n)){alert('Use a name without slashes');return;}
  try{await api('/api/write',{path:cwd+'/'+n,text:''});files[cwd+'/'+n]={text:'',dirty:false};cur=cwd+'/'+n;tabs();show();ls(cwd);}
  catch(e){alert(e.message);}
};

// ---------- run + problems ----------
$('tout').onclick=()=>panel('out');$('tprob').onclick=()=>panel('probs');
function panel(w){
  $('out').style.display=w==='out'?'':'none';$('probs').style.display=w==='probs'?'':'none';
  $('tout').className=w==='out'?'on':'';$('tprob').className=w==='probs'?'on':'';
}
function badge(cls,txt){$('badge').className=cls;$('badge').textContent=txt;}
function problems(){
  const P=$('probs');P.innerHTML='';
  errs.forEach(e=>{
    const d=document.createElement('div');d.className='prob sev-'+e.sev;
    d.textContent=e.sev+'  '+e.file+':'+e.line+':'+e.col+'  '+e.msg;
    d.onclick=()=>jump(cwd+'/'+e.file,e.line);P.appendChild(d);
  });
  const n=errs.filter(e=>e.sev==='Error').length;
  $('tprob').textContent='Problems ('+errs.length+')';
  if(n)panel('probs');
}
async function jump(p,line){
  await openFile(p);if(cur!==p)return;
  const t=$('ta'),lines=t.value.split('\n');
  let a=0;for(let i=0;i<line-1&&i<lines.length;i++)a+=lines[i].length+1;
  t.focus();t.setSelectionRange(a,a+(lines[line-1]||'').length);t.scrollTop=Math.max(0,(line-4)*19.5);
}
$('run').onclick=async()=>{
  const top=$('topm').value.trim();
  if(!top){alert('Enter the top module name (usually the testbench)');return;}
  await saveAll();badge('','Running...');$('out').textContent='Building with Verilator (about 10 seconds)...';panel('out');
  try{
    const j=await api('/api/run',{dir:cwd,top:top});
    $('out').textContent=j.sim+'\n\n--- build log ---\n'+j.build;
    errs=j.errors;problems();gutter();
    if(!j.ok||/FAIL/.test(j.sim))badge('red',j.ok?'FAIL':'BUILD ERROR');
    else if(/PASS/.test(j.sim))badge('green','PASS');
    else badge('','Done');
    if(j.vcd){parse(j.vcd);$('wave').disabled=false;openWave();}
    else{$('wave').disabled=true;}
  }catch(e){badge('red','ERROR');$('out').textContent=e.message;}
};

// ---------- waveform pop-up ----------
function parse(txt){
  const tok=txt.split(/\s+/);let i=0,scope=[],byId={},defs=false,t=0;sigs=[];tmax=0;unit='';
  while(i<tok.length){
    const w=tok[i++];
    if(!defs){
      if(w==='$scope')scope.push(tok[i+1]);
      else if(w==='$upscope')scope.pop();
      else if(w==='$timescale')unit=' '+(tok[i+1]!=='$end'?tok[i+1]:tok[i].replace(/^[0-9]+/,''));
      else if(w==='$var'){
        const s={name:(scope[0]==='TOP'?scope.slice(2):scope.slice(1)).concat(tok[i+3]).join('.'),size:+tok[i+1],ch:[]};
        sigs.push(s);(byId[tok[i+2]]=byId[tok[i+2]]||[]).push(s);
      }else if(w==='$enddefinitions')defs=true;
      continue;
    }
    let id,val;
    if(w[0]==='#'){t=+w.slice(1);tmax=Math.max(tmax,t);continue;}
    else if(w[0]==='b'||w[0]==='B'){val=w.slice(1);id=tok[i++];}
    else if(w[0]==='r'||w[0]==='R'){i++;continue;}
    else if(w[0]!=='$'&&w.length>=2){val=w[0];id=w.slice(1);}
    else continue;
    for(const s of byId[id]||[])s.ch.push([t,val]);
  }
}
const LEFT=260,ROW=30,TOP=28;
function val(s,t){let v=null;for(const c of s.ch){if(c[0]<=t)v=c[1];else break;}
  if(v===null)return '';if(s.size>1)return /[xXzZ]/.test(v)?v:BigInt('0b'+v).toString(16);return v;}
function niceStep(){for(let p=1;;p*=10)for(const m of [1,2,5])if(p*m*scale>=80)return p*m;}
function draw(){
  const W=Math.round(Math.max(tmax,1)*scale)+LEFT+30,cv=$('cv');
  cv.width=W;cv.height=sigs.length*ROW+TOP+10;
  const g=cv.getContext('2d');g.fillStyle='#0b1320';g.fillRect(0,0,W,cv.height);
  g.font='13px monospace';g.textBaseline='middle';
  const step=niceStep();
  for(let t=0;t<=tmax;t+=step){
    const x=LEFT+t*scale;g.strokeStyle='#223';g.beginPath();g.moveTo(x,TOP-6);g.lineTo(x,cv.height);g.stroke();
    g.fillStyle='#9fb3c8';g.fillText(t+unit,x+3,12);
  }
  sigs.forEach((s,r)=>{
    const y0=TOP+r*ROW,hi=y0+5,lo=y0+ROW-7,mid=(hi+lo)/2;
    g.fillStyle='#e6edf3';g.fillText(s.name,8,y0+ROW/2);
    let prev=null;
    s.ch.forEach(([t,v],k)=>{
      const t2=k+1<s.ch.length?s.ch[k+1][0]:tmax,x1=LEFT+t*scale,x2=LEFT+t2*scale,bad=/[xXzZ]/.test(v);
      g.strokeStyle=bad?'#ff6b6b':'#4ade80';
      if(s.size>1){g.strokeRect(x1,hi,Math.max(x2-x1,1),lo-hi);
        if(x2-x1>28){g.fillStyle='#e6edf3';g.fillText(bad?v:BigInt('0b'+v).toString(16),x1+4,mid);}}
      else{const y=v==='1'?hi:v==='0'?lo:mid;g.beginPath();
        if(prev!==null){g.moveTo(x1,prev);g.lineTo(x1,y);}else g.moveTo(x1,y);
        g.lineTo(x2,y);g.stroke();prev=y;}
    });
  });
  if(ct!==null){
    const x=LEFT+ct*scale;g.strokeStyle='#facc15';g.beginPath();g.moveTo(x,TOP-6);g.lineTo(x,cv.height);g.stroke();
    g.fillStyle='#facc15';g.textAlign='right';
    sigs.forEach((s,r)=>g.fillText(val(s,ct),LEFT-10,TOP+r*ROW+ROW/2));g.textAlign='left';
  }
}
function fit(){scale=($('wrap').clientWidth-LEFT-40)/Math.max(tmax,1);draw();}
function openWave(){$('win').hidden=false;fit();}
function place(e){
  const cv=$('cv'),r=cv.getBoundingClientRect(),x=(e.clientX-r.left)*cv.width/r.width,t=(x-LEFT)/scale;
  ct=(t>=0&&t<=tmax)?Math.round(t):null;$('ctl').textContent=ct===null?'':'Cursor: '+ct+unit;draw();
}
$('cv').onmousemove=e=>{if(!lock)place(e);};
$('cv').onclick=e=>{lock=!lock;if(!lock)place(e);};
$('zi').onclick=()=>{scale*=1.5;draw();};$('zo').onclick=()=>{scale/=1.5;draw();};$('fit').onclick=fit;
$('wave').onclick=openWave;$('wx').onclick=()=>{$('win').hidden=true;};
$('exp').onclick=()=>{
  const keep=ct;ct=null;draw();
  $('cv').toBlob(b=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='waveform.png';a.click();},'image/png');
  ct=keep;draw();
};
$('bar').onmousedown=e=>{
  if(e.target.tagName==='BUTTON')return;
  const w=$('win'),r=w.getBoundingClientRect(),dx=e.clientX-r.left,dy=e.clientY-r.top;
  const mv=ev=>{w.style.left=(ev.clientX-dx)+'px';w.style.top=(ev.clientY-dy)+'px';};
  const up=()=>{removeEventListener('mousemove',mv);removeEventListener('mouseup',up);};
  addEventListener('mousemove',mv);addEventListener('mouseup',up);
};
ls('');
</script>'''


def safe(p):
    return os.path.realpath(os.path.expanduser(p or START))


def modules_in(d):
    mods = []
    for n in sorted(os.listdir(d)):
        if n.endswith(('.v', '.sv')):
            try:
                with open(os.path.join(d, n), errors='replace') as f:
                    mods += re.findall(r'^\s*module\s+(\w+)', f.read(200000), re.M)
            except OSError:
                pass
    return mods


def ls(path):
    d = safe(path)
    if not os.path.isdir(d):
        raise ValueError('Not a folder: ' + d)
    ents = []
    for n in os.listdir(d):
        if n.startswith('.'):
            continue
        ents.append({'name': n, 'dir': os.path.isdir(os.path.join(d, n))})
    ents.sort(key=lambda e: (not e['dir'], e['name'].lower()))
    parent = os.path.dirname(d) if os.path.dirname(d) != d else None
    return {'path': d, 'parent': parent, 'entries': ents, 'modules': modules_in(d)}


def read(path):
    p = safe(path)
    if os.path.getsize(p) > 1000000:
        raise ValueError('File is too large to edit here')
    with open(p, errors='replace') as f:
        return {'text': f.read()}


def write(req):
    p = safe(req['path'])
    if not p.endswith(WRITE_OK):
        raise ValueError('Only Verilog and text files (' + ', '.join(WRITE_OK) + ') can be saved here')
    if os.path.isdir(p):
        raise ValueError('That is a folder')
    with open(p, 'w') as f:
        f.write(req.get('text', ''))
    return {'ok': True}


ERR = re.compile(r'%(Error|Warning)(?:-\w+)?: ([^:\n]+):(\d+):(\d+): (.*)')


def run(req):
    d = safe(req.get('dir'))
    top = req.get('top', '')
    if not re.fullmatch(r'\w+', top):
        raise ValueError('Invalid top module name')
    tmp = tempfile.mkdtemp(prefix='vgui_')
    try:
        names = []
        for n in os.listdir(d):
            if n.endswith(SRC) and os.path.isfile(os.path.join(d, n)):
                shutil.copy(os.path.join(d, n), tmp)
                if n.endswith(('.v', '.sv')):
                    names.append(n)
        if not names:
            raise ValueError('No .v or .sv files in this folder')
        p = subprocess.run(['verilator', '--binary', '--trace', '-Wno-fatal', '--top-module', top] + names,
                           cwd=tmp, capture_output=True, text=True, timeout=300)
        build = p.stdout + p.stderr
        errors = [{'sev': m[0], 'file': os.path.basename(m[1]), 'line': int(m[2]), 'col': int(m[3]), 'msg': m[4]}
                  for m in ERR.findall(build)]
        if p.returncode != 0:
            return {'ok': False, 'build': build, 'sim': 'BUILD FAILED. See Problems.', 'vcd': '', 'errors': errors}
        q = subprocess.run(['./obj_dir/V' + top], cwd=tmp, capture_output=True, text=True, timeout=120)
        sim = q.stdout + q.stderr
        vcds = glob.glob(os.path.join(tmp, '*.vcd'))
        vcd = open(vcds[0]).read() if vcds else ''
        if not vcd:
            sim += '\nNo .vcd produced: the testbench needs $dumpfile and $dumpvars.'
        return {'ok': True, 'build': build, 'sim': sim, 'vcd': vcd, 'errors': errors}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='application/json'):
        data = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok(self):
        return self.headers.get('Host') in ('127.0.0.1:%d' % PORT, 'localhost:%d' % PORT) \
            and self.headers.get('X-VGUI') == TOKEN

    def _api(self, fn):
        if not self._ok():
            return self._send(403, json.dumps({'error': 'Forbidden: open the link the TASMEEM launcher opened (it ends with ?t=...)'}))
        try:
            self._send(200, json.dumps(fn()))
        except Exception as e:
            self._send(400, json.dumps({'error': str(e)}))

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == '/':
            return self._send(200, PAGE, 'text/html; charset=utf-8')
        if u.path == '/api/ls':
            return self._api(lambda: ls(q.get('path')))
        if u.path == '/api/read':
            return self._api(lambda: read(q.get('path')))
        self._send(404, json.dumps({'error': 'Not found'}))

    def do_POST(self):
        u = urlparse(self.path)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        except ValueError:
            return self._send(400, json.dumps({'error': 'Bad request'}))
        if u.path == '/api/write':
            return self._api(lambda: write(req))
        if u.path == '/api/run':
            return self._api(lambda: run(req))
        self._send(404, json.dumps({'error': 'Not found'}))


if __name__ == '__main__':
    print('Verilator GUI running at http://127.0.0.1:%d/?t=%s  (Ctrl+C to stop)' % (PORT, TOKEN))
    http.server.ThreadingHTTPServer((HOST, PORT), H).serve_forever()
