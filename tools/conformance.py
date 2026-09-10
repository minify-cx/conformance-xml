#!/usr/bin/env python3
"""Independent format conformance runner for Minify++."""
from __future__ import annotations
import argparse, datetime, decimal, hashlib, html, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORMAT=ROOT.name.removeprefix("conformance-")
RESULTS=ROOT/"results/latest.json"
EXT={"json":".json","jsx":".tsx","xml":".xml","svg":".svg"}[FORMAT]

def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def load(p): return json.loads(Path(p).read_text())
def save(p,v):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def lock():
 p=ROOT/".state/sources.lock.json"; return load(p) if p.exists() else {}

def sync():
 specs=load(ROOT/"config/sources.json")
 state=lock()
 for name,spec in specs.items():
  dst=ROOT/spec["path"]; dst.parent.mkdir(parents=True,exist_ok=True)
  if spec["type"]=="git":
   if dst.exists():
    subprocess.run(["git","fetch","--prune","origin"],cwd=dst,check=True)
   else:
    cmd=["git","clone","--filter=blob:none","--no-checkout","--no-tags",spec["url"],str(dst)]
    subprocess.run(cmd,check=True)
   if spec.get("sparse"):
    subprocess.run(["git","sparse-checkout","init","--cone"],cwd=dst,check=True)
    subprocess.run(["git","sparse-checkout","set",*spec["sparse"]],cwd=dst,check=True)
   subprocess.run(["git","checkout","--detach",spec["revision"]],cwd=dst,check=True)
   revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=dst,text=True).strip()
   if revision!=spec["revision"]: raise SystemExit(f"{name}: revision mismatch")
  else:
   data=urllib.request.urlopen(spec["url"],timeout=120).read()
   digest=hashlib.sha256(data).hexdigest()
   if digest!=spec["sha256"]: raise SystemExit(f"{name}: SHA-256 mismatch: {digest}")
   if dst.exists(): shutil.rmtree(dst)
   dst.mkdir(parents=True)
   with tempfile.NamedTemporaryFile() as f:
    f.write(data); f.flush()
    with tarfile.open(f.name,"r:*") as tf:
     base=dst.resolve()
     for member in tf.getmembers():
      target=(dst/member.name).resolve()
      if os.path.commonpath((base,target))!=str(base): raise SystemExit("unsafe archive member")
     tf.extractall(dst,filter="data")
   revision=spec["sha256"]
  state[name]={"url":spec["url"],"revision":revision,"synced_at":now()}
 save(ROOT/".state/sources.lock.json",state)
 print(json.dumps(state,sort_keys=True))

def json_value(text):
 def pairs(items):
  seen=set(); out={}
  for k,v in items:
   if k in seen: raise ValueError(f"duplicate key: {k}")
   seen.add(k); out[k]=v
  return out
 return json.loads(text,parse_float=decimal.Decimal,parse_int=decimal.Decimal,object_pairs_hook=pairs)


def minifier_identity(exe):
 probe=subprocess.run([str(exe),'--version'],capture_output=True,text=True)
 text=(probe.stdout or probe.stderr or '').strip()
 m=re.search(r'(\d+\.\d+\.\d+)',text)
 commit=None
 parent=Path(exe).resolve().parent
 if (parent/'.git').exists():
  r=subprocess.run(['git','-C',str(parent),'rev-parse','HEAD'],capture_output=True,text=True)
  if r.returncode==0: commit=r.stdout.strip()
 return {'name':'Minify++','version':m.group(1) if m else text,'version_string':text,'commit':commit,'path':str(exe)}

def oracle_identity():
 if FORMAT=="json":
  return {'name':'python-stdlib-json','implementation':sys.implementation.name,'python_version':sys.version.split()[0],'parser':'json.loads with parse_float/int=Decimal and duplicate-key-rejecting object_pairs_hook'}
 if FORMAT=="jsx":
  cp=subprocess.run(["node","-e",'const ts=require("typescript");process.stdout.write(JSON.stringify({node:process.version,typescript:ts.version}))'],capture_output=True,text=True,cwd=ROOT)
  try: d=json.loads(cp.stdout or '{}')
  except Exception: d={}
  return {'name':'typescript-tsx-oracle','node':d.get('node'),'typescript':d.get('typescript')}
 from lxml import etree
 import lxml
 return {'name':'lxml','version':getattr(lxml,'__version__','unknown'),'libxml2':'.'.join(str(x) for x in etree.LIBXML_VERSION)}

def xml_value(text):
 from lxml import etree
 if "<!DOCTYPE" in text.upper(): raise ValueError("doctype")
 parser=etree.XMLParser(resolve_entities=False,load_dtd=False,no_network=True,recover=False,remove_blank_text=False,strip_cdata=False)
 root=etree.fromstring(text.encode("utf-8"),parser)
 return etree.tostring(root,method="c14n",with_comments=False)

def jsx_values(sources):
 oracle=ROOT/"tools/jsx_oracle.js"
 cp=subprocess.run(["node",str(oracle)],input=json.dumps(sources),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if cp.returncode: raise RuntimeError(cp.stderr[-2000:])
 return json.loads(cp.stdout)

def source_root():
 specs=load(ROOT/"config/sources.json"); key=next(iter(specs)); dst=ROOT/specs[key]["path"]
 if FORMAT=="xml" and (dst/"xmlconf").exists(): return dst/"xmlconf"
 return dst

def extract(source,out,limit):
 rows=[]; skipped={}
 patterns={"json":("*.json",),"jsx":("*.tsx","*.jsx"),"xml":("*.xml",),"svg":("*.svg",)}[FORMAT]
 paths=[]
 for pattern in patterns: paths.extend(source.rglob(pattern))
 for p in sorted(set(paths)):
  rel=p.relative_to(source).as_posix()
  if any(x in p.parts for x in ("node_modules",".git","resources","support")):
   reason="support-or-vendored-path"
  elif FORMAT=="json" and p.name.startswith(("n_","i_")):
   reason="invalid-or-implementation-defined"
  elif FORMAT=="json" and "test_parsing" not in p.parts:
   reason="non-parsing-fixture"
  elif FORMAT=="jsx" and not ("tests/cases/conformance/jsx/" in rel or "tests/cases/conformance/react/" in rel):
   reason="outside-jsx-conformance-tree"
  elif FORMAT=="svg" and (".sub." in p.name or ".tentative." in p.name):
   reason="server-or-tentative-fixture"
  else: reason=None
  if reason:
   skipped[reason]=skipped.get(reason,0)+1; continue
  try: text=p.read_text(encoding="utf-8")
  except (UnicodeDecodeError,OSError):
   skipped["non-utf8-or-unreadable"]=skipped.get("non-utf8-or-unreadable",0)+1; continue
  if FORMAT in ("xml","svg"):
   try: xml_value(text)
   except Exception as e:
    reason="doctype-or-parser-inapplicable" if "doctype" in str(e).lower() else "source-parser-rejected"
    skipped[reason]=skipped.get(reason,0)+1; continue
  elif FORMAT=="json":
   try: json_value(text)
   except Exception as e:
    reason="duplicate-key" if "duplicate key" in str(e) else "source-parser-rejected"
    skipped[reason]=skipped.get(reason,0)+1; continue
  ident=hashlib.sha256((rel+"\0"+text).encode()).hexdigest()[:16]
  rows.append({"id":ident,"suite":next(iter(load(ROOT/"config/sources.json"))),"source":rel,"text":text})
  if limit and len(rows)>=limit: break
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
 summary={"eligible":len(rows),"excluded":skipped}; save(out.with_suffix(".summary.json"),summary); print(json.dumps(summary,sort_keys=True))

def executable(value):
 p=Path(value).expanduser()
 if p.exists(): return p.resolve()
 found=shutil.which(value)
 if not found: raise SystemExit(f"executable not found: {value}")
 return Path(found)

def minify(cases,exe):
 outputs={}; errors={}
 with tempfile.TemporaryDirectory() as td:
  entries=[]
  for i,c in enumerate(cases):
   p=Path(td)/f"case-{i:06d}{EXT}"; p.write_text(c["text"]); entries.append((c,p))
  def group(items):
   cp=subprocess.run([str(exe),*[str(p) for _,p in items]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   produced=[(c,p,p.with_name(p.stem+".min"+p.suffix)) for c,p in items]
   if cp.returncode==0 and all(q.exists() for _,_,q in produced):
    for c,_,q in produced: outputs[c["id"]]=q.read_text()
   elif len(items)>1:
    mid=len(items)//2; group(items[:mid]); group(items[mid:])
   else:
    c,_,q=produced[0]
    if q.exists(): outputs[c["id"]]=q.read_text()
    else: errors[c["id"]]=(cp.stderr or cp.stdout or "no output produced")[-2000:]
  for start in range(0,len(entries),500): group(entries[start:start+500])
 return outputs,errors

def compare(before,after):
 try:
  if FORMAT=="json": a,b=json_value(before),json_value(after)
  elif FORMAT in ("xml","svg"): a,b=xml_value(before),xml_value(after)
  else:
   a,b=jsx_values([before,after])
   if not a["ok"]: return "source-rejected",{"before":a}
   if not b["ok"]: return "parser-rejected",{"after":b}
   return ("pass",{}) if a["tokens"]==b["tokens"] else ("token-difference",{"before":a,"after":b})
 except Exception as e:
  try:
   if FORMAT=="json": json_value(before)
   elif FORMAT in ("xml","svg"): xml_value(before)
  except Exception as source_error: return "source-rejected",{"error":str(source_error)}
  return "parser-rejected",{"error":str(e)}
 return ("pass",{}) if a==b else ("semantic-difference",{"before":repr(a)[:4000],"after":repr(b)[:4000]})

def execute(cases_path,exe,result):
 cases=[json.loads(x) for x in cases_path.read_text().splitlines() if x.strip()]
 started=time.time(); outputs,errors=minify(cases,exe); rows=[]; counts={}
 for c in cases:
  if c["id"] in errors: status,evidence="minify-error",{"error":errors[c["id"]]}
  else: status,evidence=compare(c["text"],outputs.get(c["id"],""))
  counts[status]=counts.get(status,0)+1
  row={k:c[k] for k in ("id","suite","source")}; row["status"]=status
  if status!="pass": row.update(input=c["text"],output=outputs.get(c["id"]),evidence=evidence)
  rows.append(row)
 summary_path=cases_path.with_suffix(".summary.json")
 eligibility=load(summary_path) if summary_path.exists() else {"eligible":len(cases),"excluded":{}}
 payload={"schema_version":1,"format":FORMAT,"generated_at":now(),"duration_seconds":round(time.time()-started,3),"source_revisions":lock(),"eligibility":eligibility,"minifier":minifier_identity(exe),"oracle":oracle_identity(),"total":len(rows),"counts":counts,"results":rows}
 save(result,payload); save(ROOT/"results/history"/f'{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.json',payload)
 print(json.dumps(counts,sort_keys=True))
 failures=sum(counts.get(k,0) for k in ("minify-error","parser-rejected","semantic-difference","token-difference"))
 return 1 if failures else 0

def smoke_cases():
 values={
 "json":[('object','{"name":"Minify++","values":[1,true,null,"x\\ny"]}'),('unicode','{"snowman":"\\u2603","n":1.25e+2}')],
 "jsx":[("element",'const view = <section className="card">Hello <b>{name}</b></section>;'),("tsx",'const Box = <T,>(x:T) => <div data-value={x}>{String(x)}</div>;')],
 "xml":[("namespaces",'<?xml version="1.0"?><root xmlns:x="urn:x"><x:item id="1"> a &amp; b </x:item><!--c--></root>'),("pi",'<?xml version="1.0"?><root><?work keep?><empty /></root>')],
 "svg":[("shapes",'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0 L10 10"/><text x="1" y="5">Hi</text></svg>'),("foreign",'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div xmlns="http://www.w3.org/1999/xhtml"> a <b>b</b> </div></foreignObject></svg>')]
 }[FORMAT]
 return [{"id":n,"suite":"smoke","source":n,"text":s} for n,s in values]

def provenance_text(data):
 min=data.get('minifier',{}); ora=data.get('oracle',{}); revs=data.get('source_revisions',{})
 bits=[f"<strong>Minify++</strong> {html.escape(str(min.get('version','')))}{(' ('+html.escape(str(min.get('commit',''))))[:9]+')' if min.get('commit') else ''}",
       f"<strong>oracle</strong> {html.escape(str(ora.get('name','')))} {html.escape(str(ora.get('version',ora.get('typescript',''))))}"]
 for k,v in revs.items():
  bits.append(f"<strong>{html.escape(k)}</strong> <code>{html.escape(str(v.get('revision','')))[:12]}</code>")
 return '<p class="provenance">' + ' &middot; '.join(bits) + '</p>'

def dashboard(result):
 data=load(result); cards="".join(f"<li><strong>{html.escape(k)}</strong><span>{v}</span></li>" for k,v in sorted(data["counts"].items()))
 bad=[r for r in data["results"] if r["status"]!="pass"][:200]
 rows="".join(f'<tr><td>{html.escape(r["status"])}</td><td>{html.escape(r["source"])}</td><td><code>{r["id"]}</code></td></tr>' for r in bad) or '<tr><td colspan="3">No non-pass cases.</td></tr>'
 g=ROOT/"generated/latest.html"; g.parent.mkdir(exist_ok=True)
 g.write_text(f'<section class="hero"><p class="eyebrow">{FORMAT.upper()} conformance</p><h1>Minify++ {FORMAT.upper()} evidence</h1><p>{data["total"]} independently sourced eligible cases. Generated {data["generated_at"]}.</p></section><ul class="stats">{cards}</ul>{provenance_text(data)}<section><h2>Non-pass evidence</h2><table><thead><tr><th>Status</th><th>Source</th><th>ID</th></tr></thead><tbody>{rows}</tbody></table></section>')
 (ROOT/"public/results").mkdir(parents=True,exist_ok=True); shutil.copy(result,ROOT/"public/results/latest.json")
 if shutil.which("nift"):
  subprocess.run(["nift","build","--all"],cwd=ROOT,check=True)
 else:
  # Keep the checked-in dashboard reviewable in minimal environments. Nift
  # remains the canonical CI/site builder; this fallback mirrors the single
  # page template without introducing a second source format.
  head=(ROOT/"templates/head.html").read_text().replace("$[title]",f"Minify++ {FORMAT.upper()} conformance").replace("@path('public/assets/css/style.css')","assets/css/style.css")
  page=(ROOT/"templates/template.html").read_text().replace('@input("templates/head.html")',head).replace("@content",g.read_text()).replace("@path('public/assets/js/script.js')","assets/js/script.js")
  (ROOT/"public/index.html").write_text(page)
  shutil.copytree(ROOT/"content/assets",ROOT/"public/assets",dirs_exist_ok=True)
 verify_dashboard(result,ROOT/"public/index.html",ROOT/"public/results/latest.json")


def verify_dashboard(result_path,index_path,published_path):
 # Prove the freshly built dashboard reflects exactly this completed run: the
 # published JSON must carry the same counts, source revisions and generation
 # timestamp, and the rendered page must contain no unresolved Nift
 # directives.
 data=load(result_path); pub=load(published_path)
 for key in ("counts","source_revisions","minifier","oracle","generated_at"):
  if pub.get(key)!=data.get(key):
   raise SystemExit(f"dashboard mismatch: {key} differs between result and published copy")
 text=Path(index_path).read_text()
 for token in ("@path(","@pathto(","@input(","@content"):
  if token in text: raise SystemExit(f"unresolved Nift directive in dashboard: {token}")
 print("dashboard verified: published JSON matches run and page has no unresolved directives")

def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
 s.add_parser("sync")
 e=s.add_parser("extract"); e.add_argument("--source",type=Path); e.add_argument("--output",type=Path,default=ROOT/f"work/{FORMAT}-cases.jsonl"); e.add_argument("--limit",type=int)
 for name in ("run","smoke"):
  q=s.add_parser(name); q.add_argument("--minify-bin",default="../minify/minify"); q.add_argument("--results",type=Path,default=RESULTS); q.add_argument("--dashboard",action="store_true")
  if name=="run": q.add_argument("--cases",type=Path,default=ROOT/f"work/{FORMAT}-cases.jsonl")
 d=s.add_parser("dashboard"); d.add_argument("--results",type=Path,default=RESULTS)
 a=p.parse_args()
 if a.cmd=="sync": sync(); return 0
 if a.cmd=="extract": extract(a.source or source_root(),a.output,a.limit); return 0
 if a.cmd=="dashboard": dashboard(a.results); return 0
 if a.cmd=="smoke":
  path=ROOT/f"work/smoke-{FORMAT}.jsonl"; path.parent.mkdir(exist_ok=True); path.write_text("".join(json.dumps(x)+"\n" for x in smoke_cases()))
 else: path=a.cases
 rc=execute(path,executable(a.minify_bin),a.results)
 if a.dashboard: dashboard(a.results)
 return rc
if __name__=="__main__": raise SystemExit(main())
