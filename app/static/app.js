const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const api = (p, b) => fetch(p, b ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}
                                 : {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json());
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const redact = s => esc(s).replace(/\[([A-Z_]+)_REDACTED\]/g, '<mark>$1</mark>');

let CAND = null, DISABLED = new Set(), CID = 'sim:demo';

// ── nav ───────────────────────────────────────────────────────────────
$$('.step').forEach(b => b.onclick = () => go(b.dataset.screen));
function go(name){
  $$('.step').forEach(s => s.classList.toggle('active', s.dataset.screen === name));
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === name));
  if (name === 'live') refreshLive();
}
function markDone(name){ $$('.step').forEach(s => { if (s.dataset.screen === name) s.classList.add('done'); }); }

// ── status ────────────────────────────────────────────────────────────
async function status(){
  const s = await api('/api/status');
  const b = $('#runtimeBadge'), hermes = s.runtime.startsWith('hermes');
  b.textContent = 'runtime: ' + s.runtime;
  b.className = 'badge ' + (hermes ? 'live' : 'stub');
  b.title = hermes ? 'Hermes agent runtime active'
                   : 'Hermes runtime not installed yet — deterministic stand-in walker, same entry point';
  $('#chatRuntime').textContent = s.runtime; $('#chatRuntime').className = 'badge sm ' + (hermes?'live':'stub');
  return s;
}

// ── 1. import ─────────────────────────────────────────────────────────
$('#loadFixture').onclick = () => doImport({});
$('#file').onchange = e => { const f = e.target.files[0]; if(!f) return;
  const r = new FileReader(); r.onload = () => doImport({content: JSON.parse(r.result)}); r.readAsText(f); };

async function doImport(body){
  const r = await api('/api/import', body);
  if (r.error) return alert(r.error);
  const st = r.stats, red = Object.values(st.redactions).reduce((a,b)=>a+b,0);
  $('#importStats').className = 'stats';
  $('#importStats').innerHTML = [
    ['chats', st.chats], ['messages kept', r.count], ['service events dropped', st.dropped_service],
    ['identifiers redacted', red], ['owner turns', st.speakers.owner||0], ['customer turns', st.speakers.customer||0]
  ].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
  $('#msgCount').textContent = r.count + ' messages';
  $('#messages').innerHTML = r.messages.map(m =>
    `<div class="msg ${m.speaker}"><div class="meta">${m.speaker} · #${m.message_id} · ${m.timestamp.replace('T',' ')} · ${m.language_hint}</div>${redact(m.text)}</div>`).join('');
  $('#extractBtn').disabled = false;
  markDone('import'); card();
}

$('#extractBtn').onclick = async () => {
  const btn = $('#extractBtn'); btn.disabled = true; btn.textContent = 'Analyzing…';
  const c = await api('/api/extract');
  btn.textContent = 'Analyze with Qwen →'; btn.disabled = false;
  if (c.error) return alert(c.error);
  CAND = c; renderReview(c);
  const live = c._source === 'qwen';
  const n = $('#extractNote'); n.className = 'note' + (live ? '' : ' warnbox');
  n.innerHTML = live
    ? `<b>Qwen</b> returned a schema-valid candidate.<br>candidate hash ${c._candidate_hash.slice(7,23)}`
    : `<b>Mock learning result</b> — this is an intentionally saved candidate for the displayed input, not a live model call.<br>candidate hash ${c._candidate_hash.slice(7,23)}`;
  card(); go('review');
};

// ── 2. review ─────────────────────────────────────────────────────────
const confClass = c => c >= .85 ? 'hi' : c >= .72 ? 'mid' : 'lo';
const evById = id => (CAND.evidence || []).find(e => e.id === id);

function evidenceBlock(ids){
  if (!ids || !ids.length) return '';
  const items = ids.map(evById).filter(Boolean).map(e =>
    `<div class="evbox"><q>${redact(e.redacted_excerpt)}</q>
     <div class="src">msg ${e.source.message_ids.join(', ')} · ${e.source.timestamp_start.replace('T',' ')} · chat ${e.source.chat_id_hash.slice(7,17)}</div></div>`).join('');
  return `<details class="ev"><summary>Evidence from history (${ids.length})</summary>${items}</details>`;
}

function ruleCard(kind, r, label, statement){
  const key = kind + ':' + r.id, off = DISABLED.has(key);
  return `<div class="rule ${off?'off':''}">
    <div class="rule-hd"><div><span class="rule-id">${label}</span></div>
      <span class="conf ${confClass(r.confidence)}">${Math.round(r.confidence*100)}%</span></div>
    <p>${esc(statement)}</p>
    ${evidenceBlock(r.evidence_ids)}
    <button class="toggle" data-key="${key}">${off?'Enable':'Disable this rule'}</button></div>`;
}

function renderReview(c){
  $('#statusPill').textContent = c.status;
  $('#stages').innerHTML = (c.states||[]).map(s =>
    `<span class="stg ${s.initial?'init':''} ${s.terminal?'term':''}">${s.id}</span>`).join('');
  $('#rules').innerHTML =
    (c.policies||[]).map(p => ruleCard('policy', p, p.id, p.statement)).join('') +
    (c.transitions||[]).map(t => ruleCard('transition', t, t.id,
      `${t.from} → ${t.to} when ${t.trigger.intent}` +
      (t.guards && t.guards.all_slots_present ? `, once ${t.guards.all_slots_present.join(', ')} are known` : ''))).join('');
  $('#slots').innerHTML = (c.slots||[]).map(s =>
    `<div class="slot"><div><code>${s.id}</code><div class="t">${s.type} · asks “${esc(s.prompts.en)}”</div></div>
     <span class="conf ${confClass(s.confidence)}">${Math.round(s.confidence*100)}%</span></div>`).join('');
  $('#unresolved').innerHTML = (c.unresolved_questions||[]).length
    ? c.unresolved_questions.map(u => `<div class="uq">${esc(u.question)}<span class="c">confidence ${Math.round(u.confidence*100)}% · stays a question, never becomes automation</span></div>`).join('')
    : '<div class="empty">None.</div>';
  $$('.toggle').forEach(b => b.onclick = () => {
    DISABLED.has(b.dataset.key) ? DISABLED.delete(b.dataset.key) : DISABLED.add(b.dataset.key);
    renderReview(CAND);
  });
}

$('#approveBtn').onclick = async () => {
  const a = await api('/api/approve', {disabled_rules: [...DISABLED]});
  if (a.error) return alert(a.error);
  const box = $('#approvalBox'); box.className = 'note';
  box.innerHTML = `<b>Approved v${a.recipe_version}</b><br>hash ${a.content_hash.slice(7,31)}<br>
    from candidate ${(a.source_candidate_hash||'').slice(7,23)}<br>
    owner edits: ${a.owner_edits.length}${a.owner_edits.length?' — '+a.owner_edits.map(e=>e.target).join(', '):''}<br>
    immutable · the compiler accepts only this hash`;
  $('#statusPill').textContent = 'approved v' + a.recipe_version; $('#statusPill').className = 'pill ok';
  $('#compileBtn').classList.remove('hidden'); markDone('review'); card();
};

$('#compileBtn').onclick = async () => {
  const r = await api('/api/compile');
  const cr = r.compile_report || {}, tr = r.test_report || {};
  const pending = r._source === 'pending';
  const box = $('#compileBox'); box.className = 'note' + (pending ? ' warnbox' : '');
  const passed = (tr.scenarios||[]).filter(s => s.passed === true).length;
  box.innerHTML = pending
    ? `<b>Compiler not wired yet</b><br>engine.compile (Devin's lane) is not installed.<br>
       ${ (tr.scenarios||[]).length } scenarios derived from the approved recipe, awaiting the real compiler:<br>
       ${(tr.scenarios||[]).map(s=>'· '+s.name).join('<br>')}`
    : `<b>Compiled</b> ${cr.status}<br>approved hash ${(cr.approved_hash||'').slice(7,27)}<br>
       tests ${passed}/${(tr.scenarios||[]).length} passed<br>
       rejected constructs: ${(cr.rejected||[]).length}`;
  card();
};

// ── 3. live ───────────────────────────────────────────────────────────
const QUICK = ['Hi nak chocolate cake 1kg', 'Sabtu ni, delivery', 'yes correct',
               'whats the price for 2kg', 'can you do it tomorrow? urgent', 'I want to speak to a human'];
$('#quick').innerHTML = QUICK.map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join('');
$$('#quick button').forEach(b => b.onclick = () => { $('#chatInput').value = b.dataset.q; $('#chatForm').requestSubmit(); });

$('#chatForm').onsubmit = async e => {
  e.preventDefault();
  const text = $('#chatInput').value.trim(); if (!text) return;
  $('#chatInput').value = '';
  const r = await api('/api/chat/send', {conversation_id: CID, text});
  if (r.error) return alert(r.error);
  refreshLive();
};

async function refreshLive(){
  const t = await api('/api/chat/transcript', {conversation_id: CID});
  const st = await api('/api/chat/state', {conversation_id: CID});
  $('#chat').innerHTML = t.turns.length ? t.turns.map(tn => {
    const p = tn.payload, out = (p.actions||[]).filter(a => a.type === 'send');
    const escalated = (p.actions||[]).some(a => a.type === 'escalate');
    return `<div class="bub cust"><div class="who">customer · #${p.in.message_id}</div>${esc(p.in.text)}</div>` +
      out.map(a => `<div class="bub ${escalated?'esc':'bot'}"><div class="who">${escalated?'escalated to owner':'agent · '+p.runtime}</div>${esc(a.text)}</div>`).join('');
  }).join('') : '<div class="empty">Send a message as a new customer.</div>';
  $('#chat').scrollTop = 1e6;

  $('#stateBox').innerHTML = st.empty ? 'No conversation yet.' : `
    <div><span class="k">state</span> <span class="v">${st.state}</span></div>
    <div><span class="k">recipe</span> ${st.recipe_id} v${st.recipe_version}</div>
    <div><span class="k">language</span> ${st.detected_language}</div>
    <div><span class="k">slots</span><br>${Object.entries(st.slots).map(([k,v])=>`<span class="chip">${k}=${esc(v)}</span>`).join('')||'—'}</div>
    <div><span class="k">still missing</span><br>${(st.missing_required_slots||[]).map(s=>`<span class="chip">${s}</span>`).join('')||'—'}</div>
    <div><span class="k">seen msg ids</span> ${(st.seen_message_ids||[]).join(', ')}</div>
    ${st.escalation ? `<div><span class="k">escalation</span> <span class="v">${st.escalation.reason}</span></div>` : ''}`;

  $('#trace').innerHTML = t.turns.length ? [...t.turns].reverse().map(tn => { const x = tn.payload.trace;
    return `<div class="tr"><span class="t">${x.transition || x.asked ? (x.transition || 'ask:'+x.asked) : (x.result||'—')}</span>
      <span class="d"><br>msg #${x.message_id} · ${x.state_in} → ${x.state_out||x.state_in}
      ${x.policy?'<br>policy '+x.policy:''}${(x.evidence_ids||[]).length?'<br>evidence '+x.evidence_ids.join(', '):''}
      <br>runtime ${x.runtime}${x.note?'<br>⚠ '+x.note:''}</span></div>`; }).join('')
    : '<div class="empty">No turns yet.</div>';
  card();
}

// ── result card ───────────────────────────────────────────────────────
async function card(){
  const c = await api('/api/result-card');
  const d = c.discovered, o = c.owner_control, v = c.validation;
  $('#resultCard').innerHTML = `
    <div class="hd">Input</div><b>${c.input.conversations}</b> conversations · <b>${c.input.messages}</b> messages
    <div class="hd">Resipi discovered</div>
    <b>${d.stages}</b> workflow stages<br><b>${d.required_fields}</b> required customer fields<br>
    <b>${d.evidence_backed_rules}</b> evidence-backed rules<br><b>${d.unresolved_questions}</b> unresolved questions
    ${d.mean_policy_confidence?`<br>mean confidence <b>${d.mean_policy_confidence}</b>`:''}
    <div class="hd">Owner control</div>
    ${o.approved ? `approved v<b>${o.version}</b> · ${o.edits} edits<br>hash ${o.hash}` : 'awaiting approval'}
    <div class="hd">Validation</div>
    <b>${v.scenarios_passed}</b>/<b>${v.scenarios_total}</b> compiler scenarios passed<br>
    <b>${v.conversations_handled}</b> live conversations · <b>${v.escalations}</b> escalated`;
}

$('#resetBtn').onclick = async () => {
  await api('/api/reset');
  CAND = null; DISABLED = new Set();
  location.reload();
};

status(); card();
