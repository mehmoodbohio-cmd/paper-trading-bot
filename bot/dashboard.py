"""
Builds docs/index.html: a live dashboard of what the bot is doing.
GitHub Pages serves the docs/ folder as a website. The page refreshes itself
every 5 minutes; the bot rebuilds it every 30 minutes.
"""

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as C
from .universe import asset_class, currency, pretty

ROOT = Path(__file__).resolve().parent.parent
BERLIN = ZoneInfo("Europe/Berlin")


def build(pf, journal, scan, now, buy_block=None):
    fx = pf.get("fx") or 1.08
    holdings = []
    for t, p in pf["positions"].items():
        px = (pf.get("live_prices") or {}).get(t) or p["last_price"]
        val = p["units"] * (px / fx if currency(t) == "USD" else px)
        cls = asset_class(t)
        holdings.append(dict(
            t=pretty(t), sym=t, cls=cls, value=round(val, 2), cost=round(p["cost_eur"], 2),
            pnl=round(val - p["cost_eur"], 2), pnl_pct=(val / p["cost_eur"] - 1) if p["cost_eur"] else 0,
            entry=p["entry_price"], px=px, ccy=currency(t), opened=p["opened"],
            stop=p["entry_price"] * (1 - C.STOP_LOSS[cls]),
            trail=p["peak"] * (1 - C.TRAILING_STOP[cls]) if p["peak"] > p["entry_price"] else None,
            reasons=p.get("reasons", [])))
    value = pf["cash"] + sum(h["value"] for h in holdings)

    trades = []
    for j in reversed(journal[-200:]):
        trades.append(dict(time=j["time"], side=j["side"], t=pretty(j["ticker"]), sym=j["ticker"],
                           eur=j["eur"], fee=j["fee"], conf=j.get("confidence"), reasons=j["reasons"],
                           check=j.get("check")))
    graded = [j for j in journal if j.get("check")]

    # keep the chart light: at most ~400 points
    hist = pf.get("history", [])
    step = max(1, len(hist) // 400)
    hist = hist[::step] + ([hist[-1]] if hist and hist[-1] not in hist[::step] else [])

    shortlist = []
    for t in scan.get("shortlist", []):
        s = scan.get("scores", {}).get(t, {})
        shortlist.append(dict(t=pretty(t), sym=t, cls=asset_class(t), score=s.get("score"),
                              tech=s.get("tech"), fund=s.get("fund"),
                              why=(s.get("good", [])[:2] + s.get("reasons", [])[:2]),
                              held=t in pf["positions"]))

    data = dict(
        updated=now.astimezone(BERLIN).isoformat(), started=pf.get("started"),
        value=round(value, 2), start=C.STARTING_CASH_EUR, cash=round(pf["cash"], 2),
        day_start=pf.get("day_start_value", C.STARTING_CASH_EUR), fees=round(pf.get("fees_paid", 0), 2),
        n_trades=len(journal), right=sum(1 for j in graded if j["check"]["right"]), graded=len(graded),
        holdings=holdings, trades=trades, history=hist, mood=pf.get("mood", {}),
        skipped=pf.get("last_skipped", []), shortlist=shortlist, block=buy_block,
        scan_counts=scan.get("counts", {}), max_pos=C.MAX_POSITIONS,
    )
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    (out / "index.html").write_text(PAGE.replace("__DATA__", payload))
    (out / ".nojekyll").write_text("")


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Paper Trading Bot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#0f172a;--mute:#64748b;--line:#e5e7eb;--up:#059669;--down:#dc2626;
--accent:#4f46e5;--warn:#d97706;--chip:#f1f5f9;--b1:#94a3b8;--b2:#f59e0b;--b3:#a855f7}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0b0f17;--card:#121826;--ink:#e5e7eb;
--mute:#8b95a7;--line:#222b3b;--up:#34d399;--down:#f87171;--accent:#818cf8;--chip:#1b2333;--b1:#64748b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,system-ui,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;margin-bottom:18px}
h1{font-size:22px;margin:0;letter-spacing:-.02em}.sub{color:var(--mute);font-size:13px}
.live{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--mute)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--up);box-shadow:0 0 0 0 var(--up);animation:p 2s infinite}
.dot.stale{background:var(--warn);animation:none}
@keyframes p{0%{box-shadow:0 0 0 0 rgba(5,150,105,.5)}70%{box-shadow:0 0 0 8px rgba(5,150,105,0)}100%{box-shadow:0 0 0 0 rgba(5,150,105,0)}}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.k .l{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em}
.k .v{font:600 24px/1.2 Inter;margin-top:4px;font-variant-numeric:tabular-nums}.k .d{font-size:13px;margin-top:2px}
.up{color:var(--up)}.down{color:var(--down)}.mute{color:var(--mute)}
h2{font-size:15px;margin:0 0 10px;display:flex;justify-content:space-between;align-items:center}
.grid{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
svg text{fill:var(--mute);font:11px Inter}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--mute);margin-top:6px}
.legend i{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.chips{display:flex;flex-direction:column;gap:8px}
.chip{display:flex;gap:10px;align-items:flex-start;padding:10px;border-radius:10px;background:var(--chip);font-size:13px}
.chip b{display:block}.badge{font:600 11px Inter;padding:2px 8px;border-radius:99px;white-space:nowrap}
.ok{background:rgba(5,150,105,.15);color:var(--up)}.cautious{background:rgba(217,119,6,.15);color:var(--warn)}
.risk-off{background:rgba(220,38,38,.15);color:var(--down)}.unknown{background:var(--line);color:var(--mute)}
.BUY{background:rgba(5,150,105,.15);color:var(--up)}.SELL{background:rgba(220,38,38,.15);color:var(--down)}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;font-weight:500;color:var(--mute);font-size:12px;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top;font-variant-numeric:tabular-nums}
.r{text-align:right}.tk{font-weight:600}.cls{font-size:11px;color:var(--mute)}
.scroll{overflow-x:auto}
details{border-bottom:1px solid var(--line);padding:10px 0}details:last-child{border:0}
summary{cursor:pointer;list-style:none;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}
.why{margin:8px 0 2px 4px;padding-left:16px;color:var(--mute);font-size:13px}.why li{margin:2px 0}
.time{font:500 12px 'JetBrains Mono',monospace;color:var(--mute);min-width:92px}
.feed{max-height:560px;overflow:auto}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;width:90px;display:inline-block;vertical-align:middle}
.bar>span{display:block;height:100%;background:var(--accent)}
.alert{background:rgba(217,119,6,.12);border:1px solid rgba(217,119,6,.35);color:var(--warn);border-radius:12px;padding:10px 14px;margin-bottom:14px;font-size:14px}
.empty{color:var(--mute);font-size:14px;padding:8px 0}
footer{color:var(--mute);font-size:12px;margin-top:24px;text-align:center}
.pill{font-size:11px;padding:1px 7px;border-radius:99px;background:var(--chip);color:var(--mute)}
</style></head><body><div class="wrap" id="app"></div>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const eur = (x, s=false) => (s && x>0 ? '+' : '') + (x<0?'-':'') + '€' + Math.abs(x).toFixed(2);
const pct = x => (x>0?'+':'') + (x*100).toFixed(1) + '%';
const cl = x => x>0.0001 ? 'up' : x<-0.0001 ? 'down' : 'mute';
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const berlin = iso => new Date(iso).toLocaleString('en-GB',{timeZone:'Europe/Berlin',weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const clsName = c => ({crypto:'Crypto',us_stock:'US stock',eu_stock:'German stock'}[c]||c);

function chart(){
  const H = D.history; if (H.length < 2) return '<div class="empty">The chart appears after a few runs.</div>';
  const W=640, Ht=220, P={l:44,r:10,t:10,b:24};
  const series = [{k:'v',name:'Bot',col:'var(--accent)',w:2.5}];
  const names = [...new Set(H.flatMap(h => Object.keys(h.b||{})))];
  const cols=['var(--b1)','var(--b2)','var(--b3)'];
  names.forEach((n,i)=>series.push({k:n,name:'€100 in '+n,col:cols[i%3],w:1.4,dash:'4 3'}));
  const get=(h,s)=> s.k==='v'? h.v : (h.b||{})[s.k];
  const vals=H.flatMap(h=>series.map(s=>get(h,s))).filter(v=>v!=null);
  let lo=Math.min(...vals,100), hi=Math.max(...vals,100); const pad=(hi-lo)*0.1||1; lo-=pad; hi+=pad;
  const t0=new Date(H[0].t), t1=new Date(H[H.length-1].t), span=(t1-t0)||1;
  const X=t=>P.l+(new Date(t)-t0)/span*(W-P.l-P.r), Y=v=>P.t+(hi-v)/(hi-lo)*(Ht-P.t-P.b);
  let g='';
  for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4, y=Y(v);
    g+=`<line x1="${P.l}" x2="${W-P.r}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${P.l-6}" y="${y+4}" text-anchor="end">€${v.toFixed(0)}</text>`;}
  g+=`<line x1="${P.l}" x2="${W-P.r}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--mute)" stroke-dasharray="2 4" opacity=".6"/>`;
  const days=[...new Set(H.map(h=>h.t.slice(0,10)))];
  days.forEach(d=>{const h=H.find(x=>x.t.startsWith(d)); const x=X(h.t);
    g+=`<text x="${x}" y="${Ht-6}" text-anchor="middle">${new Date(h.t).toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'Europe/Berlin'})}</text>`;});
  series.slice().reverse().forEach(s=>{const pts=H.filter(h=>get(h,s)!=null).map(h=>`${X(h.t).toFixed(1)},${Y(get(h,s)).toFixed(1)}`);
    if(pts.length>1) g+=`<polyline fill="none" stroke="${s.col}" stroke-width="${s.w}" ${s.dash?`stroke-dasharray="${s.dash}"`:''} stroke-linejoin="round" points="${pts.join(' ')}"/>`;});
  const last=H[H.length-1]; g+=`<circle cx="${X(last.t)}" cy="${Y(last.v)}" r="4" fill="var(--accent)"/>`;
  return `<svg viewBox="0 0 ${W} ${Ht}" width="100%" role="img" aria-label="Portfolio value over time">${g}</svg>
  <div class="legend">${series.map(s=>`<span><i style="background:${s.col}"></i>${esc(s.name)}</span>`).join('')}</div>`;
}

function render(){
  const total=D.value-D.start, day=D.value-D.day_start;
  const ageMin=(Date.now()-new Date(D.updated))/60000;
  const holdVal=D.holdings.reduce((a,h)=>a+h.value,0);
  let h=`<header><div><h1>Paper Trading Bot</h1><div class="sub">Pretend money only · started ${berlin(D.started)} with €${D.start.toFixed(0)}</div></div>
  <div class="live"><span class="dot ${ageMin>75?'stale':''}"></span>${ageMin>75?'No update for '+Math.round(ageMin)+' min':'Live'} · updated ${berlin(D.updated)}</div></header>`;
  if (D.block) h+=`<div class="alert">⏸ ${esc(D.block)}</div>`;
  h+=`<div class="kpis">
   <div class="card k"><div class="l">Portfolio</div><div class="v">€${D.value.toFixed(2)}</div><div class="d ${cl(total)}">${eur(total,1)} (${pct(total/D.start)}) since start</div></div>
   <div class="card k"><div class="l">Today</div><div class="v ${cl(day)}">${eur(day,1)}</div><div class="d ${cl(day)}">${pct(day/D.day_start)}</div></div>
   <div class="card k"><div class="l">Invested / cash</div><div class="v">€${holdVal.toFixed(2)}</div><div class="d mute">€${D.cash.toFixed(2)} cash · ${D.holdings.length}/${D.max_pos} positions</div></div>
   <div class="card k"><div class="l">Trades</div><div class="v">${D.n_trades}</div><div class="d mute">€${D.fees.toFixed(2)} paid in fees</div></div>
   <div class="card k"><div class="l">Right after 24h</div><div class="v">${D.graded?Math.round(100*D.right/D.graded)+'%':'–'}</div><div class="d mute">${D.right}/${D.graded} trades graded</div></div>
  </div>`;
  const mood=Object.entries(D.mood).map(([k,v])=>`<div class="chip"><span class="badge ${v[0]}">${esc(v[0])}</span><div><b>${({stocks:'US stocks',eu_stocks:'German stocks',crypto:'Crypto'})[k]||k}</b>${esc(v[1])}</div></div>`).join('');
  h+=`<div class="grid"><div class="card"><h2>Bot vs. doing nothing</h2>${chart()}</div>
   <div class="card"><h2>Market mood</h2><div class="chips">${mood||'<div class="empty">Waiting for first run.</div>'}</div></div></div>`;

  const rows=D.holdings.map(x=>`<tr><td><span class="tk">${esc(x.t)}</span><div class="cls">${clsName(x.cls)}</div></td>
    <td class="r">€${x.value.toFixed(2)}</td><td class="r ${cl(x.pnl)}">${eur(x.pnl,1)}<div class="cls ${cl(x.pnl)}">${pct(x.pnl_pct)}</div></td>
    <td class="r">${x.entry.toPrecision(5)} → ${x.px.toPrecision(5)} <span class="cls">${x.ccy}</span></td>
    <td class="r">${x.stop.toPrecision(5)}${x.trail?`<div class="cls">trail ${x.trail.toPrecision(5)}</div>`:''}</td>
    <td class="mute">${berlin(x.opened)}</td></tr>`).join('');
  h+=`<div class="card" style="margin-bottom:14px"><h2>Holding now</h2>${rows?`<div class="scroll"><table><tr><th>Asset</th><th class="r">Value</th><th class="r">Profit/loss</th><th class="r">Bought → now</th><th class="r">Sells below</th><th>Since</th></tr>${rows}</table></div>`:'<div class="empty">Nothing - all in cash. The bot waits until a setup is good enough.</div>'}</div>`;

  const feed=D.trades.map(t=>`<details><summary><span class="time">${berlin(t.time)}</span><span class="badge ${t.side}">${t.side}</span>
     <span class="tk">${esc(t.t)}</span><span>€${t.eur.toFixed(2)}</span>${t.conf!=null?`<span class="pill">confidence ${Math.round(t.conf*100)}%</span>`:''}
     ${t.check?`<span class="pill ${t.check.right?'up':'down'}">${t.check.right?'✓ right':'✗ wrong'} after 24h (${pct(t.check.move)})</span>`:''}</summary>
     <ul class="why">${t.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul></details>`).join('');
  const sl=D.shortlist.map(s=>`<tr><td><span class="tk">${esc(s.t)}</span>${s.held?' <span class="pill">held</span>':''}<div class="cls">${clsName(s.cls)}</div></td>
     <td><span class="bar"><span style="width:${Math.round((s.score||0)*100)}%"></span></span> <span class="cls">${(s.score||0).toFixed(2)}</span></td>
     <td class="mute" style="font-size:12px">${s.why.map(esc).join(' · ')}</td></tr>`).join('');
  h+=`<div class="grid"><div class="card"><h2>Trade feed <span class="sub">tap a trade to see why</span></h2><div class="feed">${feed||'<div class="empty">No trades yet.</div>'}</div></div>
   <div class="card"><h2>Today's shortlist</h2><div class="sub" style="margin:-6px 0 8px">Best 15 of ${D.scan_counts.stocks||'?'} stocks + ${D.scan_counts.crypto||'?'} coins</div>
   <div class="scroll"><table>${sl}</table></div>
   <h2 style="margin-top:16px">Why it didn't buy</h2>${D.skipped.length?`<ul class="why" style="margin:0">${D.skipped.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:'<div class="empty">Nothing was blocked in the latest run.</div>'}</div></div>`;
  h+=`<footer>Rebuilt by the bot every 30 minutes · page refreshes every 5 minutes · not investment advice</footer>`;
  $('#app').innerHTML=h;
}
render();
</script></body></html>
"""
