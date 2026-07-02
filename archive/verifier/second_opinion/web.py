"""A local web UI for Second Opinion — the visual demo, built in React.

Zero build step: React is loaded from a CDN and JSX is transpiled in the browser, so it
still runs with one command and no npm. The Python backend uses the same pipeline as the
CLI (real-mode when ANTHROPIC_API_KEY is set, and cached so re-verifying is instant).

    python -m second_opinion.web
    # open http://localhost:8000
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer

from .pipeline import Pipeline
from .providers import classify_route

_PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Second Opinion</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>
  :root{
    --bg:#0b0d12; --bg2:#0f131a; --card:#141924; --line:#232a37; --ink:#eef1f6; --dim:#98a1b2;
    --accent:#7c6cff; --green:#34d399; --amber:#fbbf24; --red:#f87171;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{background:radial-gradient(1200px 600px at 50% -10%, #1a2030 0%, var(--bg) 55%);
    color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:760px;margin:0 auto;padding:56px 20px 100px}
  .brand{display:flex;align-items:center;gap:11px;margin-bottom:8px}
  .brand h1{font-size:24px;font-weight:700;margin:0;letter-spacing:-.4px}
  .badge{margin-left:auto;font-size:11px;color:var(--dim);border:1px solid var(--line);
    padding:4px 9px;border-radius:999px}
  .tag{color:var(--dim);margin:0 0 26px;font-size:15px}
  .panel{background:linear-gradient(180deg,#161b26,#121721);border:1px solid var(--line);
    border-radius:16px;padding:16px;box-shadow:0 20px 60px -30px rgba(0,0,0,.7)}
  textarea{width:100%;min-height:120px;background:transparent;color:var(--ink);border:0;
    outline:none;resize:vertical;font-size:15.5px;line-height:1.55;font-family:inherit}
  textarea::placeholder{color:#5c657a}
  .bar{display:flex;align-items:center;gap:12px;margin-top:8px;padding-top:12px;border-top:1px solid var(--line)}
  button{background:linear-gradient(180deg,#8b7bff,#6b5aff);color:#fff;border:0;border-radius:11px;
    padding:11px 22px;font-size:15px;font-weight:600;cursor:pointer;transition:transform .06s, opacity .2s}
  button:hover{transform:translateY(-1px)} button:disabled{opacity:.5;cursor:default;transform:none}
  .link{color:var(--dim);font-size:13px;cursor:pointer;background:0;border:0;font-family:inherit}
  .link:hover{color:var(--ink)}
  .mock{margin:18px 0 0;padding:11px 13px;border-radius:11px;font-size:13px;
    background:rgba(251,191,36,.08);color:var(--amber);border:1px solid rgba(251,191,36,.25)}
  .summary{display:flex;align-items:center;gap:10px;margin:26px 2px 6px;font-size:19px;font-weight:600}
  .dot{width:9px;height:9px;border-radius:50%}
  .sec{color:var(--dim);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;margin:22px 2px 10px}
  .claim{border:1px solid var(--line);border-left:3px solid var(--line);background:var(--card);
    border-radius:12px;padding:14px 15px;margin:9px 0;animation:rise .4s ease both}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .claim.contradicted{border-left-color:var(--red)}
  .claim.unverified{border-left-color:var(--amber)}
  .claim.supported{border-left-color:var(--green);opacity:.66}
  .claim.not_checkable{border-left-color:#3a4150;opacity:.55}
  .chead{display:flex;align-items:center;gap:9px}
  .verdict{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em}
  .contradicted .verdict{color:var(--red)} .unverified .verdict{color:var(--amber)}
  .supported .verdict{color:var(--green)} .not_checkable .verdict{color:var(--dim)}
  .dimb{font-size:9.5px;font-weight:600;color:var(--dim);border:1px solid var(--line);padding:1px 7px;border-radius:999px;text-transform:uppercase;letter-spacing:.06em}
  .conf{margin-left:auto;display:flex;align-items:center;gap:7px;color:var(--dim);font-size:11px}
  .track{width:52px;height:4px;border-radius:3px;background:#2a3140;overflow:hidden}
  .fill{height:100%;border-radius:3px}
  .ctext{margin:8px 0 0;font-size:15.5px;line-height:1.5}
  .why{color:var(--dim);font-size:14px;margin:7px 0 0}
  .src{margin-top:9px}
  .src a{display:inline-flex;align-items:center;gap:6px;color:var(--accent);text-decoration:none;
    font-size:13px;background:rgba(124,108,255,.1);border:1px solid rgba(124,108,255,.25);
    padding:5px 10px;border-radius:8px}
  .src a:hover{background:rgba(124,108,255,.18)}
  .nosrc{color:var(--dim);font-size:13px;margin-top:8px}
  .loading{display:flex;align-items:center;gap:10px;color:var(--dim);margin:24px 2px;font-size:15px}
  .pulse{display:flex;gap:5px}
  .pulse span{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pp 1s infinite ease-in-out}
  .pulse span:nth-child(2){animation-delay:.15s} .pulse span:nth-child(3){animation-delay:.3s}
  @keyframes pp{0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1)}}
  .foot{color:#5c657a;font-size:12px;margin-top:44px;border-top:1px solid var(--line);padding-top:16px}
</style></head>
<body><div id="root"></div>
<script type="text/babel">
const {useState} = React;
const EXAMPLE = "The Eiffel Tower is 450 metres tall. According to a 2019 Stanford study by Chen et al., AI models collapse above one trillion parameters. Also, 15% of 2.3 million is 3.45 million, and Queen Elizabeth II is the current reigning monarch of the UK. Honestly, it's the most beautiful city on earth.";
const COLOR={contradicted:"var(--red)",unverified:"var(--amber)",supported:"var(--green)",not_checkable:"#3a4150"};
const ORDER={contradicted:0,unverified:1,supported:2,not_checkable:3};
const DIM={standard:"fact",citation:"source",numeric:"math",temporal:"recency"};

function Shield(){
  return (<svg width="26" height="26" viewBox="0 0 24 24" fill="none">
    <path d="M12 2l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V5l7-3z" fill="url(#g)" stroke="#a89bff" strokeWidth="1"/>
    <path d="M8.5 12l2.3 2.3 4.7-4.8" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <defs><linearGradient id="g" x1="5" y1="2" x2="19" y2="21"><stop stopColor="#8b7bff"/><stop offset="1" stopColor="#5b48d8"/></linearGradient></defs>
  </svg>);
}

function Claim({v,i}){
  const flagged = v.label==="contradicted"||v.label==="unverified";
  return (
    <div className={"claim "+v.label} style={{animationDelay:(i*0.05)+"s"}}>
      <div className="chead">
        <span className="verdict">{v.label.replace("_"," ")}</span>
        <span className="dimb">{DIM[v.dimension]||"fact"}</span>
        {v.label!=="not_checkable" &&
          <span className="conf"><span className="track"><span className="fill"
            style={{width:Math.round(v.confidence*100)+"%",background:COLOR[v.label]}}/></span>
            {Math.round(v.confidence*100)}%</span>}
      </div>
      <div className="ctext">{v.claim}{v.label==="not_checkable" && <span style={{color:"var(--dim)"}}> — judgment, not checked</span>}</div>
      {flagged && v.rationale && <div className="why">{v.rationale}</div>}
      {v.source_url
        ? <div className="src"><a href={v.source_url} target="_blank" rel="noreferrer">↳ {v.source_title||v.source_url}</a></div>
        : (v.label==="unverified" && <div className="nosrc">no source found — flagged, not asserted</div>)}
    </div>
  );
}

function App(){
  const [text,setText]=useState("");
  const [loading,setLoading]=useState(false);
  const [res,setRes]=useState(null);
  const [err,setErr]=useState("");

  async function verify(){
    const t=text.trim(); if(!t)return;
    setLoading(true); setRes(null); setErr("");
    try{
      const r=await fetch("/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});
      setRes(await r.json());
    }catch(e){ setErr(String(e)); }
    setLoading(false);
  }

  const vs = res ? [...res.verdicts].sort((a,b)=>ORDER[a.label]-ORDER[b.label]) : [];
  const flagged = vs.filter(v=>v.label==="contradicted"||v.label==="unverified");
  const calm = vs.filter(v=>v.label==="supported"||v.label==="not_checkable");
  const anyFlag = flagged.some(v=>v.label==="contradicted");

  return (
    <div className="wrap">
      <div className="brand"><Shield/><h1>Second Opinion</h1>
        <span className="badge">grounded AI fact-check</span></div>
      <p className="tag">Paste an AI answer. It checks the facts, sources, math, and recency — with receipts, and never bluffs.</p>

      <div className="panel">
        <textarea value={text} onChange={e=>setText(e.target.value)}
          placeholder="Paste an answer from ChatGPT, Claude, Gemini…"/>
        <div className="bar">
          <button onClick={verify} disabled={loading||!text.trim()}>{loading?"Checking…":"Verify"}</button>
          <button className="link" onClick={()=>setText(EXAMPLE)}>try an example</button>
        </div>
      </div>

      {loading && <div className="loading"><div className="pulse"><span/><span/><span/></div>
        Checking each claim against live sources…</div>}
      {err && <div className="mock" style={{color:"var(--red)",borderColor:"rgba(248,113,113,.3)",background:"rgba(248,113,113,.08)"}}>Error: {err}</div>}

      {res && <div>
        {res.mock && <div className="mock">Mock mode — no API key set, so this uses canned data.
          Set ANTHROPIC_API_KEY for real, grounded verification.</div>}
        <div className="summary">
          <span className="dot" style={{background: res.nothing?"#3a4150":(anyFlag?"var(--red)":"var(--green)")}}/>
          {res.summary}
        </div>
        {!res.nothing && flagged.length>0 && <div>
          <div className="sec">Needs your eyes</div>
          {flagged.map((v,i)=><Claim key={i} v={v} i={i}/>)}</div>}
        {!res.nothing && calm.length>0 && <div>
          <div className="sec">Checked — looks fine</div>
          {calm.map((v,i)=><Claim key={i} v={v} i={i}/>)}</div>}
      </div>}

      <div className="foot">Decompose → verify each claim against external evidence → calibrated verdict.
        Flagged claims come first; verified ones stay quiet. Same engine as the CLI.</div>
    </div>
  );
}
ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
</script>
</body></html>"""


def _serialize(report):
    verdicts = []
    for v in report.verdicts:
        src = v.primary_source
        verdicts.append({
            "label": v.label.value,
            "confidence": round(v.confidence, 2),
            "claim": v.claim.text,
            "rationale": v.rationale,
            "source_title": src.source_title if src else "",
            "source_url": src.source_url if src else "",
            "dimension": classify_route(v.claim.text),  # how it was checked
        })
    return {
        "mock": bool(report.mock_stages),
        "summary": report.summary_line(),
        "nothing": report.is_nothing_to_verify,
        "verdicts": verdicts,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/verify":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            text = json.loads(self.rfile.read(length) or b"{}").get("text", "").strip()
        except json.JSONDecodeError:
            text = ""
        if not text:
            self._send(400, b'{"error":"no text"}', "application/json")
            return
        report = Pipeline().run(text)
        self._send(200, json.dumps(_serialize(report)).encode("utf-8"), "application/json")

    def log_message(self, *args):  # keep the console quiet
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    mode = "REAL (grounded)" if os.environ.get("ANTHROPIC_API_KEY") else "MOCK (no API key)"
    print(f"Second Opinion web UI — {mode}")
    print(f"  open  http://localhost:{port}")
    ThreadingTCPServer.allow_reuse_address = True
    with ThreadingTCPServer(("", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nbye")


if __name__ == "__main__":
    main()
