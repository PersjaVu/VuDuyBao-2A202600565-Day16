"""Tạo dashboard index.html từ kết quả benchmark.

Đọc react_runs.jsonl + reflexion_runs.jsonl trong một thư mục output (và dataset
gốc để lấy difficulty), rồi xuất một file HTML self-contained gồm:
  1. KPI tổng quan + bảng so sánh ReAct vs Reflexion.
  2. Ước tính chi phí & thời gian chạy (có ô nhập đơn giá để tính lại).
  3. Phân rã theo loại lỗi (failure_mode) cho mỗi agent.
  4. Phân tích phục hồi: recovered / unrecovered / regression, kèm chiến thuật
     reflection của các câu KHÔNG phục hồi được.
  5. EM theo độ khó (difficulty).
  6. Bảng từng câu: đáp án ReAct/Reflexion ai đúng, loại lỗi, click để xem quỹ đạo.

Cách dùng:
    python make_dashboard.py --run-dir outputs/my_test_set \
        --dataset data/my_test_set.json --out index.html
"""
from __future__ import annotations
import json
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@app.command()
def main(
    run_dir: str = "outputs/my_test_set",
    dataset: str = "data/my_test_set.json",
    out: str = "index.html",
) -> None:
    run = Path(run_dir)
    react = _load_jsonl(run / "react_runs.jsonl")
    reflexion = _load_jsonl(run / "reflexion_runs.jsonl")
    if not react and not reflexion:
        raise typer.BadParameter(f"Không tìm thấy dữ liệu jsonl trong {run}")

    difficulty: dict[str, str] = {}
    dpath = Path(dataset)
    if dpath.exists():
        for item in json.loads(dpath.read_text(encoding="utf-8")):
            difficulty[item.get("qid", "")] = item.get("difficulty", "?")

    payload = {"dataset": run.name, "react": react, "reflexion": reflexion, "difficulty": difficulty}
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    Path(out).write_text(html, encoding="utf-8")
    print(f"Wrote dashboard -> {out}  (react={len(react)}, reflexion={len(reflexion)}, difficulties={len(difficulty)})")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReAct vs Reflexion — Benchmark Dashboard</title>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --ink:#e2e8f0; --mut:#94a3b8; --ok:#22c55e; --bad:#ef4444; --warn:#f59e0b; --acc:#38bdf8; --line:#334155; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, Arial; background:var(--bg); color:var(--ink); padding:24px; }
  h1 { margin:0 0 4px; font-size:24px; }
  h2 { font-size:18px; margin:28px 0 12px; color:var(--acc); }
  .sub { color:var(--mut); margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .card .k { color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .card .v { font-size:26px; font-weight:700; margin-top:6px; }
  .card .d { font-size:12px; margin-top:4px; }
  table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  th, td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--line); font-size:14px; vertical-align:top; }
  th { background:#162033; color:var(--mut); position:sticky; top:0; z-index:1; }
  td.num, th.num { text-align:right; font-variant-numeric: tabular-nums; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; }
  .ok { color:var(--ok); } .bad { color:var(--bad); } .warn { color:var(--warn); }
  .pill.ok { background:rgba(34,197,94,.15); color:var(--ok); }
  .pill.bad { background:rgba(239,68,68,.15); color:var(--bad); }
  .pill.mode { background:rgba(56,189,248,.12); color:var(--acc); }
  .pill.diff { background:rgba(148,163,184,.15); color:var(--mut); }
  .up { color:var(--ok); } .down { color:var(--bad); }
  input { background:#0b1220; color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:14px; }
  .controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
  .q { max-width:360px; }
  .muted { color:var(--mut); font-size:12px; }
  .answer { max-width:200px; word-break:break-word; }
  .wrap { overflow:auto; max-height:72vh; }
  tr.qrow { cursor:pointer; }
  tr.qrow:hover { background:#16233a; }
  .detail { background:#0b1220; }
  .detail .box { padding:8px 10px; border-left:3px solid var(--acc); margin:6px 0; }
  .bar { height:8px; border-radius:4px; background:#0b1220; overflow:hidden; min-width:80px; }
  .bar > span { display:block; height:100%; }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media(max-width:800px){ .two{grid-template-columns:1fr;} }
</style>
</head>
<body>
<h1>ReAct vs Reflexion — Benchmark Dashboard</h1>
<div class="sub" id="meta"></div>

<h2>1. Tổng quan</h2>
<div class="grid" id="cards"></div>

<h2>2. Bảng so sánh chi tiết</h2>
<div class="wrap"><table id="cmp"></table></div>

<h2>3. Ước tính chi phí & thời gian chạy</h2>
<div class="controls">
  <label class="muted">Đơn giá ($ / 1 triệu token):
    <input id="rate" type="number" value="0" step="0.01" style="width:120px"></label>
  <span class="muted">(model free = 0$. Nhập giá để ước tính cho model trả phí)</span>
</div>
<div class="wrap"><table id="cost"></table></div>

<h2>4. Phân rã theo loại lỗi (failure mode)</h2>
<div class="wrap"><table id="fmode"></table></div>

<h2>5. Phân tích phục hồi (Recovery)</h2>
<div class="grid" id="recCards"></div>
<div class="two" style="margin-top:14px">
  <div>
    <h3 class="muted">❌ Câu KHÔNG phục hồi được (cả 2 đều sai)</h3>
    <p class="muted" style="margin:-4px 0 8px">Vì sao không phục hồi: sau khi reflect và thử lại, Evaluator vẫn chấm sai — thường do bằng chứng cần thiết không có trong context được cấp, hoặc model lặp lại lỗi suy luận cũ nên reflection không đổi được kết quả. Lý do cụ thể của từng câu ở cột "Vì sao".</p>
    <div class="wrap"><table id="unrec"></table></div>
  </div>
  <div>
    <h3 class="muted">✅ Câu Reflexion CỨU được (ReAct sai → Reflexion đúng)</h3>
    <div class="wrap"><table id="rec"></table></div>
  </div>
</div>

<h2>6. EM theo độ khó (difficulty)</h2>
<div class="wrap"><table id="diff"></table></div>

<h2>7. Đáp án từng câu — click vào dòng để xem quỹ đạo & reflection</h2>
<div class="controls">
  <input id="search" class="q" placeholder="Lọc theo câu hỏi / qid / đáp án / loại lỗi...">
  <label class="muted"><input type="checkbox" id="onlyDiff"> Chỉ hiện câu 2 agent KHÁC kết quả</label>
  <span class="muted" id="qcount"></span>
</div>
<div class="wrap"><table id="perq"></table></div>

<script>
const DATA = __DATA__;
const DIFF = DATA.difficulty || {};
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const fmtPct = x => (x*100).toFixed(1)+'%';

function agg(records){
  const n = records.length || 1;
  const correct = records.filter(r=>r.is_correct).length;
  const tok = records.reduce((s,r)=>s+(r.token_estimate||0),0);
  const lat = records.reduce((s,r)=>s+(r.latency_ms||0),0);
  const att = records.reduce((s,r)=>s+(r.attempts||0),0);
  return { count:records.length, correct, em:correct/n, tokens:tok, latency:lat,
           avgTok:tok/n, avgLat:lat/n, avgAtt:att/n };
}
const R = agg(DATA.react), F = agg(DATA.reflexion);
document.getElementById('meta').textContent =
  `Dataset: ${DATA.dataset} · ReAct: ${R.count} · Reflexion: ${F.count} · Tổng records: ${R.count+F.count}`;

// join by qid
const byqid = {};
DATA.react.forEach(r=>{ const o=byqid[r.qid]=byqid[r.qid]||{qid:r.qid}; o.react=r; o.q=r.question; o.gold=r.gold_answer; });
DATA.reflexion.forEach(r=>{ const o=byqid[r.qid]=byqid[r.qid]||{qid:r.qid}; o.reflexion=r; o.q=o.q||r.question; o.gold=o.gold||r.gold_answer; });
const rows = Object.values(byqid);

const recovered = rows.filter(r=>r.react&&r.reflexion&&!r.react.is_correct&&r.reflexion.is_correct);
const unrecovered = rows.filter(r=>r.react&&r.reflexion&&!r.react.is_correct&&!r.reflexion.is_correct);
const regression = rows.filter(r=>r.react&&r.reflexion&&r.react.is_correct&&!r.reflexion.is_correct);

// --- Cards ---
const cards = [
  ['ReAct EM', fmtPct(R.em), `${R.correct}/${R.count} đúng`],
  ['Reflexion EM', fmtPct(F.em), `${F.correct}/${F.count} đúng`],
  ['EM cải thiện', (F.em>=R.em?'+':'')+((F.em-R.em)*100).toFixed(1)+' pp', F.em>=R.em?'Reflexion tốt hơn':'ReAct tốt hơn'],
  ['Reflexion cứu được', String(recovered.length), 'câu ReAct sai → Reflexion đúng'],
  ['Không phục hồi', String(unrecovered.length), 'cả 2 agent đều sai'],
];
document.getElementById('cards').innerHTML = cards.map(c=>
  `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div><div class="d muted">${c[2]}</div></div>`).join('');

// --- Comparison table ---
function delta(a,b,unit='',inv=false){
  const d=b-a; const cls = (inv? d<0 : d>0) ? 'up' : (d===0?'':'down');
  return `<span class="${cls}">${d>0?'+':''}${d.toFixed(2)}${unit}</span>`;
}
document.getElementById('cmp').innerHTML = `
  <tr><th>Metric</th><th class="num">ReAct</th><th class="num">Reflexion</th><th class="num">Δ (Rfx − ReAct)</th></tr>
  <tr><td>Exact Match (EM)</td><td class="num">${fmtPct(R.em)}</td><td class="num">${fmtPct(F.em)}</td><td class="num">${delta(R.em*100,F.em*100,' pp')}</td></tr>
  <tr><td>Số câu đúng</td><td class="num">${R.correct}/${R.count}</td><td class="num">${F.correct}/${F.count}</td><td class="num">${delta(R.correct,F.correct)}</td></tr>
  <tr><td>Avg attempts</td><td class="num">${R.avgAtt.toFixed(2)}</td><td class="num">${F.avgAtt.toFixed(2)}</td><td class="num">${delta(R.avgAtt,F.avgAtt,'',true)}</td></tr>
  <tr><td>Avg tokens / câu</td><td class="num">${R.avgTok.toFixed(0)}</td><td class="num">${F.avgTok.toFixed(0)}</td><td class="num">${delta(R.avgTok,F.avgTok,'',true)}</td></tr>
  <tr><td>Avg latency / câu (ms)</td><td class="num">${R.avgLat.toFixed(0)}</td><td class="num">${F.avgLat.toFixed(0)}</td><td class="num">${delta(R.avgLat,F.avgLat,'',true)}</td></tr>
`;

// --- Cost table ---
function renderCost(){
  const rate = parseFloat(document.getElementById('rate').value)||0;
  const cost = t => (t/1e6*rate);
  const row=(name,a)=>`<tr><td>${name}</td>
      <td class="num">${a.tokens.toLocaleString()}</td>
      <td class="num">${a.avgTok.toFixed(0)}</td>
      <td class="num">$${cost(a.tokens).toFixed(4)}</td>
      <td class="num">${(a.latency/1000).toFixed(1)}s</td>
      <td class="num">${(a.avgLat/1000).toFixed(2)}s</td></tr>`;
  const tot={tokens:R.tokens+F.tokens,avgTok:(R.tokens+F.tokens)/((R.count+F.count)||1),
             latency:R.latency+F.latency,avgLat:(R.latency+F.latency)/((R.count+F.count)||1)};
  document.getElementById('cost').innerHTML = `
    <tr><th>Agent</th><th class="num">Tổng tokens</th><th class="num">Token/câu</th>
        <th class="num">Cost ($)</th><th class="num">Tổng thời gian</th><th class="num">Thời gian/câu</th></tr>
    ${row('ReAct',R)} ${row('Reflexion',F)}
    <tr style="font-weight:700;background:#162033">${row('TỔNG',tot).slice(4)}</tr>`;
}
document.getElementById('rate').addEventListener('input', renderCost);
renderCost();

// --- Failure mode breakdown ---
function modeCounts(records){ const m={}; records.forEach(r=>m[r.failure_mode]=(m[r.failure_mode]||0)+1); return m; }
const rm=modeCounts(DATA.react), fm=modeCounts(DATA.reflexion);
const allModes=[...new Set([...Object.keys(rm),...Object.keys(fm)])].sort((a,b)=>(a==='none')-(b==='none')||a.localeCompare(b));
document.getElementById('fmode').innerHTML =
  `<tr><th>Failure mode</th><th class="num">ReAct</th><th class="num">Reflexion</th><th class="num">Δ</th></tr>`+
  allModes.map(m=>{const a=rm[m]||0,b=fm[m]||0;return `<tr>
    <td><span class="pill ${m==='none'?'ok':'mode'}">${esc(m)}</span></td>
    <td class="num">${a}</td><td class="num">${b}</td>
    <td class="num">${delta(a,b,'',m!=='none')}</td></tr>`;}).join('');

// --- Recovery cards ---
const recCards=[
  ['Recovered','ok',recovered.length,'ReAct sai → Reflexion đúng'],
  ['Unrecovered','bad',unrecovered.length,'cả 2 đều sai'],
  ['Regression','warn',regression.length,'ReAct đúng → Reflexion sai'],
];
document.getElementById('recCards').innerHTML=recCards.map(c=>
  `<div class="card"><div class="k">${c[0]}</div><div class="v ${c[1]}">${c[2]}</div><div class="d muted">${c[3]}</div></div>`).join('');

function lastReflection(rec){
  if(!rec || !rec.reflections || !rec.reflections.length) return '';
  const e=rec.reflections[rec.reflections.length-1];
  return `<div class="muted"><b>Strategy đã thử:</b> ${esc(e.next_strategy||'')}</div>`;
}
function finalReason(rec){
  if(!rec || !rec.traces || !rec.traces.length) return '';
  return rec.traces[rec.traces.length-1].reason || '';
}
document.getElementById('unrec').innerHTML =
  `<tr><th class="q">Câu hỏi</th><th>Gold</th><th>Rfx trả lời</th><th>Loại lỗi</th><th>Vì sao không phục hồi</th></tr>`+
  (unrecovered.length? unrecovered.map(r=>`<tr>
     <td class="q">${esc(r.q)}${lastReflection(r.reflexion)}</td>
     <td><b>${esc(r.gold)}</b></td>
     <td class="answer">${esc(r.reflexion.predicted_answer)}</td>
     <td><span class="pill mode">${esc(r.reflexion.failure_mode)}</span></td>
     <td class="answer muted">${esc(finalReason(r.reflexion))}</td></tr>`).join('')
   : `<tr><td colspan="5" class="muted">Không có — Reflexion phục hồi hết các câu ReAct sai 🎉</td></tr>`);

document.getElementById('rec').innerHTML =
  `<tr><th class="q">Câu hỏi</th><th>Gold</th><th>ReAct (sai)</th><th class="num">Attempts</th></tr>`+
  (recovered.length? recovered.map(r=>`<tr>
     <td class="q">${esc(r.q)}${lastReflection(r.reflexion)}</td>
     <td><b>${esc(r.gold)}</b></td>
     <td class="answer bad">${esc(r.react.predicted_answer)}</td>
     <td class="num">${r.reflexion.attempts}</td></tr>`).join('')
   : `<tr><td colspan="4" class="muted">Không có câu nào được cứu trong run này.</td></tr>`);

// --- EM by difficulty ---
function emByDiff(records){
  const g={}; records.forEach(r=>{const d=DIFF[r.qid]||'?';(g[d]=g[d]||{n:0,c:0});g[d].n++;if(r.is_correct)g[d].c++;});
  return g;
}
const rd=emByDiff(DATA.react), fd=emByDiff(DATA.reflexion);
const diffs=[...new Set([...Object.keys(rd),...Object.keys(fd)])];
const order={easy:0,medium:1,hard:2,'?':3};
diffs.sort((a,b)=>(order[a]??9)-(order[b]??9));
document.getElementById('diff').innerHTML =
  `<tr><th>Difficulty</th><th class="num">#câu</th><th class="num">ReAct EM</th><th class="num">Reflexion EM</th><th class="num">Δ</th></tr>`+
  (diffs.length? diffs.map(d=>{const a=rd[d]||{n:0,c:0},b=fd[d]||{n:0,c:0};
    const ea=a.n?a.c/a.n:0, eb=b.n?b.c/b.n:0;
    return `<tr><td><span class="pill diff">${esc(d)}</span></td>
      <td class="num">${a.n||b.n}</td>
      <td class="num">${fmtPct(ea)} <span class="muted">(${a.c}/${a.n})</span></td>
      <td class="num">${fmtPct(eb)} <span class="muted">(${b.c}/${b.n})</span></td>
      <td class="num">${delta(ea*100,eb*100,' pp')}</td></tr>`;}).join('')
   : `<tr><td colspan="5" class="muted">Không có thông tin difficulty (thiếu dataset).</td></tr>`);

// --- Per-question table (expandable) ---
function mark(rec){
  if(!rec || rec.is_correct===undefined) return '<span class="muted">—</span>';
  return rec.is_correct? '<span class="pill ok">✓</span>' : '<span class="pill bad">✗</span>';
}
function trajectory(rec){
  if(!rec) return '<span class="muted">—</span>';
  let h = (rec.traces||[]).map(t=>{
    let block = `<div class="box"><b>Attempt ${t.attempt_id}</b> — score ${t.score} · ${t.token_estimate} tok · ${(t.latency_ms/1000).toFixed(2)}s<br>
      <b>Answer:</b> ${esc(t.answer)}<br><span class="muted">${esc(t.reason)}</span>`;
    if(t.reflection){ block += `<br><span class="warn">↳ next strategy:</span> ${esc(t.reflection.next_strategy)}`; }
    return block + `</div>`;
  }).join('');
  return h || '<span class="muted">no traces</span>';
}
function renderPerQ(){
  const term=document.getElementById('search').value.toLowerCase();
  const onlyDiff=document.getElementById('onlyDiff').checked;
  const shown=rows.filter(r=>{
    if(onlyDiff && r.react && r.reflexion && (r.react.is_correct===r.reflexion.is_correct)) return false;
    if(!term) return true;
    const hay=(r.q+' '+r.qid+' '+((r.react||{}).predicted_answer||'')+' '+((r.reflexion||{}).predicted_answer||'')+' '+r.gold+' '+((r.react||{}).failure_mode||'')+' '+((r.reflexion||{}).failure_mode||'')).toLowerCase();
    return hay.includes(term);
  });
  document.getElementById('qcount').textContent=`${shown.length}/${rows.length} câu`;
  document.getElementById('perq').innerHTML =
    `<tr><th>#</th><th class="q">Câu hỏi</th><th>Khó</th><th>Gold</th>
       <th>ReAct</th><th></th><th>Reflexion</th><th></th><th class="num">Rfx att</th><th>Rfx lỗi</th></tr>`+
    shown.map((r,i)=>{
      const rc=r.react||{}, fc=r.reflexion||{};
      return `<tr class="qrow" data-i="${i}">
        <td class="muted">${i+1}</td>
        <td class="q">${esc(r.q)}<div class="muted">${esc(r.qid)}</div></td>
        <td><span class="pill diff">${esc(DIFF[r.qid]||'?')}</span></td>
        <td class="answer"><b>${esc(r.gold)}</b></td>
        <td class="answer">${esc(rc.predicted_answer)}</td><td>${mark(rc)}</td>
        <td class="answer">${esc(fc.predicted_answer)}</td><td>${mark(fc)}</td>
        <td class="num">${fc.attempts??'—'}</td>
        <td>${fc.failure_mode&&fc.failure_mode!=='none'?'<span class="pill mode">'+esc(fc.failure_mode)+'</span>':'<span class="muted">—</span>'}</td>
      </tr>
      <tr class="detail" id="d${i}" style="display:none"><td></td><td colspan="9">
        <div class="two">
          <div><b class="muted">ReAct trajectory</b>${trajectory(r.react)}</div>
          <div><b class="muted">Reflexion trajectory</b>${trajectory(r.reflexion)}</div>
        </div></td></tr>`;
    }).join('');
  document.querySelectorAll('tr.qrow').forEach(tr=>tr.addEventListener('click',()=>{
    const d=document.getElementById('d'+tr.dataset.i);
    d.style.display = d.style.display==='none'?'table-row':'none';
  }));
}
document.getElementById('search').addEventListener('input', renderPerQ);
document.getElementById('onlyDiff').addEventListener('change', renderPerQ);
renderPerQ();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app()
