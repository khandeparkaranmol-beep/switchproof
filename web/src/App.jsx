import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, Tooltip, LabelList,
} from "recharts";

/* ----------------------------- helpers ----------------------------- */
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

function money(x) {
  const a = Math.abs(x);
  if (a >= 1_000_000) return "$" + (x / 1_000_000).toFixed(2).replace(/\.00$/, "") + "M";
  if (a >= 1_000) return "$" + (x / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  if (a >= 100) return "$" + x.toFixed(0);
  return "$" + x.toFixed(2);
}
const moneyFull = (x) =>
  "$" + x.toLocaleString(undefined, { maximumFractionDigits: 0 });
const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";

function useCountUp(target, ms = 700) {
  const [v, setV] = useState(target);
  const from = useRef(target);
  const raf = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    cancelAnimationFrame(raf.current);
    const tick = (now) => {
      const t = clamp((now - start) / ms, 0, 1);
      const e = 1 - Math.pow(1 - t, 3);
      setV(a + (target - a) * e);
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, ms]);
  return v;
}

/* volume slider <-> calls (log scale) */
const MIN_CALLS = 10_000, MAX_CALLS = 50_000_000;
const callsFromSlider = (s) =>
  Math.round(MIN_CALLS * Math.pow(MAX_CALLS / MIN_CALLS, s / 100));
const sliderFromCalls = (c) =>
  clamp((100 * Math.log(c / MIN_CALLS)) / Math.log(MAX_CALLS / MIN_CALLS), 0, 100);
const callsLabel = (c) =>
  c >= 1_000_000 ? (c / 1_000_000).toFixed(c % 1_000_000 ? 1 : 0) + "M"
  : c >= 1_000 ? Math.round(c / 1_000) + "k" : String(c);

/* ----------------------------- app ----------------------------- */
export default function App() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch((import.meta.env.BASE_URL || "/") + "report.json")
      .then((r) => { if (!r.ok) throw new Error("no report.json"); return r.json(); })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <Shell><div className="card method">Couldn’t load <code>report.json</code>. Run <code>python -m switchproof --mock</code> first, then <code>npm run dev</code>.</div></Shell>;
  if (!data) return <Shell><div className="card method">Loading report…</div></Shell>;
  return <Shell><Report data={data} /></Shell>;
}

function Shell({ children }) {
  return <div className="wrap">{children}</div>;
}

/* ----------------------------- report ----------------------------- */
function Report({ data }) {
  const isDemo = data.mode === "mock";
  const f = data.models.frontier, o = data.models.open;

  const [calls, setCalls] = useState(data.assumptions.monthly_calls);
  const [price, setPrice] = useState({
    fIn: f.price_in, fOut: f.price_out, oIn: o.price_in, oOut: o.price_out,
  });
  const dflt = { fIn: f.price_in, fOut: f.price_out, oIn: o.price_in, oOut: o.price_out };

  const calc = useMemo(() => {
    const fPer = (f.avg_in_tokens / 1e6) * price.fIn + (f.avg_out_tokens / 1e6) * price.fOut;
    const oPer = (o.avg_in_tokens / 1e6) * price.oIn + (o.avg_out_tokens / 1e6) * price.oOut;
    const strong = data.routing.strong_share, weak = data.routing.weak_share;
    const today = fPer * calls;
    const allOpen = oPer * calls;
    const hybrid = (oPer * strong + fPer * weak) * calls;
    const full = data.headline.verdict === "SAFE_ALL";
    const featured = full ? today - allOpen : today - hybrid;
    return {
      fPer, oPer, today, allOpen, hybrid,
      savingsAll: today - allOpen, savingsHybrid: today - hybrid,
      featured, pctSaved: today ? featured / today : 0,
    };
  }, [calls, price, data, f, o]);

  const verdictSafe = data.headline.verdict !== "NOT_YET";
  const verdictText = {
    SAFE_ALL: "Safe to switch",
    SAFE_HYBRID: "Safe to switch — hybrid",
    NOT_YET: "Not yet",
  }[data.headline.verdict] || data.headline.verdict;
  const verdictSub = {
    SAFE_ALL: "The open model matches the frontier model across every slice of real traffic.",
    SAFE_HYBRID: "Move the safe slices to the open model and keep a few confusable intents on frontier — quality holds, cost drops.",
    NOT_YET: "The open model drifts on too much traffic. Fine-tune it or wait for a stronger release before switching.",
  }[data.headline.verdict] || "";

  return (
    <>
      <div className="top">
        <div className="brand">
          <div className="logo">
            <svg viewBox="0 0 24 24" fill="none"><path d="M4 8h11l-3-3m11 11H12l3 3" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1>SwitchProof</h1>
            <p>Prove a model switch is safe — and price the savings</p>
          </div>
        </div>
        <div className="mode-badge">
          <span className={"dot " + (isDemo ? "demo" : "live")} />
          {isDemo ? "DEMO DATA · mock models" : "REAL RESULTS · live model calls"}
        </div>
      </div>

      <div className="taskline">
        <b>{data.task.n.toLocaleString()}</b> real queries · <b>{data.task.n_intents}</b> intents ·{" "}
        <b>{f.name}</b><span className="arrow">→</span><b>{o.name}</b>
      </div>

      {/* verdict hero */}
      <div className="card hero">
        <div className={"verdict-pill " + (verdictSafe ? "safe" : "warn")}>
          {verdictSafe ? "✓" : "!"} {verdictText}
        </div>
        <p className="verdict-sub">{verdictSub}</p>
        <div className="stat-row">
          <HeroStat label="Agreement with frontier"
            value={pct(data.headline.agreement.rate)}
            ci={`95% CI ${pct(data.headline.agreement.low)}–${pct(data.headline.agreement.high)}`} />
          <HeroStat label="Accuracy after routing"
            value={pct(data.headline.quality_after_routing)} em
            ci={data.headline.all_frontier_acc != null
              ? `vs ${pct(data.headline.all_frontier_acc)} staying all-frontier`
              : `${pct(data.headline.agreement.rate)} agreement`} />
          <HeroStat label="Traffic switchable"
            value={pct(data.headline.traffic_switchable_pct)}
            ci={`${data.routing.weak_intents.length} intents kept on frontier`} />
        </div>
      </div>

      {/* savings */}
      <div className="section-title">What it saves</div>
      <div className="card savings">
        <div className="savings-grid">
          <div>
            <SavingsNumber value={calc.featured} />
            <div className="money-sub">
              <b>{pct(calc.pctSaved)}</b> off today’s spend · <b>{moneyFull(calc.featured * 12)}</b>/year
            </div>
            <div className="money-sub" style={{ color: "var(--text-faint)", marginTop: 6 }}>
              Today {moneyFull(calc.today)}/mo &nbsp;·&nbsp; Hybrid {moneyFull(calc.hybrid)}/mo
              &nbsp;·&nbsp; All-open {moneyFull(calc.allOpen)}/mo
            </div>

            <div className="control">
              <label>Monthly volume <span className="val">{callsLabel(calls)} calls/mo</span></label>
              <input type="range" min="0" max="100" step="0.5"
                value={sliderFromCalls(calls)}
                onChange={(e) => setCalls(callsFromSlider(+e.target.value))} />
            </div>

            <div className="price-grid">
              <PriceField label={`${f.name} in`} v={price.fIn} onChange={(x)=>setPrice(p=>({...p,fIn:x}))}/>
              <PriceField label={`${f.name} out`} v={price.fOut} onChange={(x)=>setPrice(p=>({...p,fOut:x}))}/>
              <PriceField label={`${o.name} in`} v={price.oIn} onChange={(x)=>setPrice(p=>({...p,oIn:x}))}/>
              <PriceField label={`${o.name} out`} v={price.oOut} onChange={(x)=>setPrice(p=>({...p,oOut:x}))}/>
            </div>
            <div className="hint">
              Prices are $/1M tokens — assumptions that scale the dollars, never the quality verdict.{" "}
              <button className="reset-btn" onClick={()=>{setPrice(dflt);setCalls(data.assumptions.monthly_calls);}}>Reset</button>
            </div>
          </div>

          <div>
            <div className="chart-card card" style={{ background: "rgba(9,14,26,0.4)" }}>
              <ScenarioChart today={calc.today} hybrid={calc.hybrid} allOpen={calc.allOpen} />
            </div>
          </div>
        </div>
      </div>

      {/* routing table */}
      <div className="section-title">Per-intent routing — where the open model is safe</div>
      <IntentTable intents={data.intents} />

      {/* samples */}
      <div className="section-title">Sample decisions</div>
      <SampleBrowser samples={data.samples} fName={f.name} oName={o.name} />

      {/* method */}
      <Method data={data} />

      <div className="foot">
        Generated {new Date(data.generated_at).toLocaleString()} · SwitchProof {isDemo ? "demo" : "live"} ·
        agreement measured against the frontier model as the live reference (Case 1)
      </div>
    </>
  );
}

/* ----------------------------- pieces ----------------------------- */
function HeroStat({ label, value, ci, em }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={"value" + (em ? " em" : "")}>{value}</div>
      <div className="ci">{ci}</div>
    </div>
  );
}

function SavingsNumber({ value }) {
  const v = useCountUp(value, 500);
  return (
    <div className="big-money">
      {money(v)}<span className="per"> /mo</span>
    </div>
  );
}

function PriceField({ label, v, onChange }) {
  return (
    <div className="price-field">
      <label>{label}</label>
      <div className="inp">
        <span>$</span>
        <input type="number" step="0.01" min="0" value={v}
          onChange={(e) => onChange(clamp(+e.target.value || 0, 0, 1000))} />
      </div>
    </div>
  );
}

function ScenarioChart({ today, hybrid, allOpen }) {
  const rows = [
    { name: "Today", label: "All frontier", v: today, fill: "#6b7896" },
    { name: "Hybrid", label: "Route safe slices", v: hybrid, fill: "#34d399" },
    { name: "All-open", label: "Naive switch", v: allOpen, fill: "#6ea8fe" },
  ];
  return (
    <div style={{ width: "100%", height: 230 }}>
      <div style={{ fontSize: 12, color: "var(--text-faint)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
        Monthly cost by strategy
      </div>
      <ResponsiveContainer width="100%" height="88%">
        <BarChart data={rows} margin={{ top: 18, right: 8, left: 8, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: "#9aa7c2", fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis hide />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,0.03)" }}
            contentStyle={{ background: "#121a2c", border: "1px solid rgba(120,145,190,0.3)", borderRadius: 10, color: "#eef2fb" }}
            formatter={(val) => [moneyFull(val) + "/mo", ""]}
            labelFormatter={(l) => rows.find(r=>r.name===l)?.label || l}
          />
          <Bar dataKey="v" radius={[8, 8, 0, 0]}>
            {rows.map((r, i) => <Cell key={i} fill={r.fill} />)}
            <LabelList dataKey="v" position="top" formatter={money} style={{ fill: "#eef2fb", fontSize: 12, fontWeight: 700 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function IntentTable({ intents }) {
  const [filter, setFilter] = useState("all");
  const counts = {
    all: intents.length,
    switch: intents.filter(i => i.action === "switch").length,
    keep: intents.filter(i => i.action === "keep_on_frontier").length,
  };
  const rows = intents.filter(i =>
    filter === "all" ? true : filter === "switch" ? i.action === "switch" : i.action === "keep_on_frontier");

  return (
    <div>
      <div className="tabs">
        {[["all","All"],["switch","Switch to open"],["keep","Keep on frontier"]].map(([k,lab]) => (
          <button key={k} className={filter===k?"active":""} onClick={()=>setFilter(k)}>
            {lab}<span className="count">{counts[k]}</span>
          </button>
        ))}
      </div>
      <div className="card intent-table">
        <div className="thead"><span>Intent</span><span style={{textAlign:"right"}}>n</span><span>Agreement + 95% CI</span><span>Action</span></div>
        {rows.map((it) => <IntentRow key={it.intent} it={it} />)}
      </div>
    </div>
  );
}

function IntentRow({ it }) {
  const hi = it.action === "switch";
  return (
    <div className="irow">
      <div>
        <span className="iname">{it.intent}</span>
        {!it.trusted && <span className="ismall" title="Small sample — widen it before relying on this slice">low-n</span>}
      </div>
      <div className="in">{it.n}</div>
      <div>
        <div className="bar-wrap">
          <div className="bar-ci" style={{ left: `${it.agree_low*100}%`, width: `${(it.agree_high-it.agree_low)*100}%` }} />
          <div className={"bar-fill " + (hi ? "hi" : "lo")} style={{ width: `${it.agreement*100}%` }} />
        </div>
        <span className="bar-pct">{pct(it.agreement)} <span style={{color:"var(--text-faint)"}}>({pct(it.agree_low,0)}–{pct(it.agree_high,0)})</span></span>
      </div>
      <div>
        <span className={"pill " + (hi ? "switch" : "keep")}>{hi ? "Switch → open" : "Keep on frontier"}</span>
        {it.switch_reason === "accuracy" && <span className="ismall" style={{color:"var(--accent)",display:"block",marginTop:4}} title="Switched because the open model matches the human label as well as the frontier — the frontier was the inconsistent one">via accuracy</span>}
      </div>
    </div>
  );
}

function SampleBrowser({ samples, fName, oName }) {
  const [only, setOnly] = useState(false);
  const rows = only ? samples.filter(s => !s.agree) : samples;
  return (
    <div>
      <div className="toggle" onClick={()=>setOnly(v=>!v)}>
        <span className={"switchbox " + (only?"on":"")} />
        Show only disagreements
      </div>
      <div className="card samples">
        <div className="srow" style={{ color: "var(--text-faint)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>
          <span>Customer message</span><span>{fName}</span><span>{oName}</span><span></span>
        </div>
        {rows.map((s, i) => (
          <div className="srow" key={i}>
            <span className="q">{s.text}</span>
            <span><span className="tag">{s.frontier}</span></span>
            <span><span className={"tag " + (s.agree ? "match" : "miss")}>{s.open}</span></span>
            <span className={"chk " + (s.agree ? "y" : "n")}>{s.agree ? "✓" : "✗"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Method({ data }) {
  const r = data.routing;
  return (
    <div className="card method">
      <h3>How this verdict is computed</h3>
      <p>
        The frontier model’s label on each real query is the <b>reference</b> — it’s what’s in production today,
        so “would users notice a change?” is just <b>how often the open model agrees with it</b>. Agreement is
        reported with a <b>Wilson 95% interval</b>, not a bare point estimate, because a number without error bars
        isn’t evidence.
      </p>
      <p>
        Each intent is a <b>slice</b>. A slice switches to the open model if it either <b>agrees ≥{" "}
        {pct(r.route_threshold,0)}</b> with the frontier, or — the subtle part — is <b>at least as accurate against
        the human label</b>, since agreement-with-the-incumbent is a safety floor, not ground truth (the frontier is
        itself inconsistent on near-duplicate intents). Slices under <b>{r.min_slice_n}</b> rows are too small to
        judge and stay on frontier. Cost is <b>real measured token counts × your price assumptions × your monthly
        volume</b>, updating live as you drag the sliders.
      </p>
      <div className="disclaimer">
        {data.mode === "mock"
          ? "Demo mode: model outputs are simulated so the whole flow runs with no API keys. Add ANTHROPIC_API_KEY and GROQ_API_KEY, run the engine again, and every number here becomes real — measured on live model calls."
          : "A portfolio case study on the public Banking77 benchmark — a working proof-of-concept, not a live service. Every number is measured on real model calls; pricing and volume are assumptions that scale the dollars, never the quality verdict."}
      </div>
    </div>
  );
}
