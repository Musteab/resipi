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
  if (name === 'orders') refreshOrders();
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
  const r = new FileReader();
  // readAsDataURL base64-encodes natively. Spreading a Uint8Array into
  // String.fromCharCode blows the call stack on any real WhatsApp export.
  r.onload = () => doImport({filename: f.name, raw_b64: String(r.result).split(',')[1]});
  r.onerror = () => alert("Could not read that file. Try exporting the chat again.");
  r.readAsDataURL(f); };

async function doImport(body){
  const r = await api('/api/import', body);
  if (r.error) { alert(r.error); return; }
  $('#importStats').className = 'stats';
  doRenderImport(r);
  $('#extractBtn').disabled = false;
  markDone('import'); card();
}

function doRenderImport(r){
  const st = r.stats, red = Object.values(st.redactions).reduce((a,b)=>a+b,0);
  $('#importStats').innerHTML = [
    ['chats', st.chats], ['messages kept', r.count], ['service events dropped', st.dropped_service],
    ['identifiers redacted', red], ['owner turns', st.speakers.owner||0], ['customer turns', st.speakers.customer||0]
  ].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
  const FMT = {txt:'WhatsApp/Telegram text export', docx:'Word document',
               pdf:'PDF', json:'Telegram JSON export', fixture:'demo bakery chats'};
  $('#msgCount').textContent = r.count + ' messages'
    + (r.format ? ' · read from ' + (FMT[r.format]||r.format) : '')
    + (r.owner_name ? ' · you are "' + r.owner_name + '"' : '');
  $('#messages').innerHTML = r.messages.map(m =>
    `<div class="msg ${m.speaker}"><div class="meta">${m.speaker} · #${m.message_id} · ${m.timestamp.replace('T',' ')} · ${m.language_hint}</div>${redact(m.text)}</div>`).join('');
}

$('#extractBtn').onclick = async () => {
  const btn = $('#extractBtn'); btn.disabled = true; btn.textContent = 'Analyzing…';
  const t0 = Date.now();
  const tick = setInterval(() => { btn.textContent = `Analyzing… ${Math.round((Date.now()-t0)/1000)}s`; }, 1000);
  const c = await api('/api/extract').catch(e => ({error: String(e)}));
  clearInterval(tick);
  btn.textContent = 'Work out my process →'; btn.disabled = false;
  if (c.error) return alert(c.error);
  CAND = c; renderReview(c);
  const live = c._source === 'qwen';
  const n = $('#extractNote'); n.className = 'note' + (live ? '' : ' warnbox');
  n.innerHTML = live
    ? `<b>Read by Qwen just now.</b><br>Worked out from your own messages.<br><span class=hashline>ref ${c._candidate_hash.slice(7,19)}</span>`
    : `<b>Using a saved result</b> — not a live read, for the same chats shown here.<br>why: ${esc(c._fallback_reason||'unknown')}<br><span class=hashline>ref ${c._candidate_hash.slice(7,19)}</span>`;
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
  $('#statusPill').textContent = 'switched on · v' + a.recipe_version; $('#statusPill').className = 'pill ok';
  $('#compileBtn').classList.remove('hidden'); markDone('review'); card();
};

$('#compileBtn').onclick = async () => {
  const r = await api('/api/compile');
  const cr = r.compile_report || {}, tr = r.test_report || {};
  const pending = r._source === 'pending';
  const box = $('#compileBox'); box.className = 'note' + (pending ? ' warnbox' : '');
  const passed = (tr.scenarios||[]).filter(s => s.passed === true).length;
  box.innerHTML = pending
    ? `<b>Not checked yet</b><br>why: ${esc(cr.reason||'unknown')}<br>
       ${ (tr.scenarios||[]).length } scenarios derived from the approved recipe, awaiting the real compiler:<br>
       ${(tr.scenarios||[]).map(s=>'· '+s.name).join('<br>')}`
    : `<b>Checked — ${passed} of ${(tr.scenarios||[]).length} tests passed.</b><br>
       Every rule was tried against a fake order before going live.<br>
       ${(cr.rejected||[]).length} unsafe rule(s) refused.<br><span class=hashline>ref ${(cr.approved_hash||'').slice(7,19)}</span>`;
  card();
};

// ── 3. live ───────────────────────────────────────────────────────────
// Ordered so clicking left-to-right completes a whole order, then the two
// safety cases. Verified end-to-end by tools/smoke.py.
const QUICK = ['Hi nak chocolate cake 1kg', 'satu je, Sabtu ni', 'delivery',
               'No 5 Jalan Bahagia', 'ya betul',
               'berapa harga 2kg?', 'I want to speak to a human'];
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

async function refreshConversations(){
  const d = await api('/api/conversations').catch(() => ({}));
  const list = d.conversations || [];
  $('#convCount').textContent = list.length || '';
  $('#convList').innerHTML = list.length ? list.map(c => `
    <button class="convitem ${c.conversation_id===CID?'sel':''} ${c.escalated?'esc':''}"
            data-cid="${esc(c.conversation_id)}">
      <div class="ci-top"><span>${esc(c.who)}</span><span class="ci-state">${esc(c.state||'')}</span></div>
      <div class="ci-meta">${c.channel} · ${c.slots} field(s) collected${c.escalated?' · needs you':''}</div>
    </button>`).join('')
    : '<div class="empty">No conversations yet.</div>';
  $$('#convList .convitem').forEach(b => b.onclick = () => { CID = b.dataset.cid; refreshLive(); });
}

async function refreshLive(){
  await refreshConversations();
  const t = await api('/api/chat/transcript', {conversation_id: CID}).catch(() => ({}));
  const st = await api('/api/chat/state', {conversation_id: CID}).catch(() => ({empty: true}));
  t.turns = t.turns || [];
  $('#chat').innerHTML = t.turns.length ? t.turns.map(tn => {
    const p = tn.payload, out = (p.actions||[]).filter(a => a.type === 'send');
    const escalated = (p.actions||[]).some(a => a.type === 'escalate');
    return `<div class="bub cust"><div class="who">customer · #${p.in.message_id}</div>${esc(p.in.text)}</div>` +
      out.map(a => `<div class="bub ${escalated?'esc':'bot'}"><div class="who">${escalated?'escalated to owner':'agent · '+p.runtime}</div>${esc(a.text)}</div>`).join('');
  }).join('') : '<div class="empty">Send a message as a new customer.</div>';
  $('#chat').scrollTop = 1e6;

  $('#stateBox').innerHTML = (st.empty || st.error) ? 'No conversation yet.' : `
    <div><span class="k">state</span> <span class="v">${st.state}</span></div>
    <div><span class="k">recipe</span> ${st.recipe_id} v${st.recipe_version}</div>
    <div><span class="k">language</span> ${st.detected_language}</div>
    <div><span class="k">slots</span><br>${Object.entries(st.slots).map(([k,v])=>`<span class="chip">${k}=${esc(v)}</span>`).join('')||'—'}</div>
    <div><span class="k">still missing</span><br>${(st.missing_required_slots||[]).map(s=>`<span class="chip">${s}</span>`).join('')||'—'}</div>
    <div><span class="k">seen msg ids</span> ${(st.seen_message_ids||[]).join(', ')}</div>
    ${st.escalation ? `<div><span class="k">escalation</span> <span class="v">${st.escalation.reason}</span></div>` : ''}`;

  refreshOrders();
  $('#trace').innerHTML = t.turns.length ? [...t.turns].reverse().map(tn => { const x = tn.payload.trace;
    return `<div class="tr"><span class="t">${x.transition || x.asked ? (x.transition || 'ask:'+x.asked) : (x.result||'—')}</span>
      <span class="d"><br>msg #${x.message_id} · ${x.state_in} → ${x.state_out||x.state_in}
      ${x.policy?'<br>policy '+x.policy:''}${(x.evidence_ids||[]).length?'<br>evidence '+x.evidence_ids.join(', '):''}
      <br>runtime ${x.runtime}${x.note?'<br>⚠ '+x.note:''}</span></div>`; }).join('')
    : '<div class="empty">No turns yet.</div>';
  card();
}

// ── orders (owner inbox) ──────────────────────────────────────────────
const SLOT_LABEL = {product:'Item', size:'Size', quantity:'Qty', fulfilment_date:'When',
                    fulfilment_method:'Pickup/delivery', delivery_address:'Address'};
const ESC_LABEL = {
  missing_price_or_availability: "Customer asked a price the agent doesn't know",
  no_rush_order_without_owner:   'Customer wants a rush order — you never promise these',
  customer_requests_human:       'Customer asked to speak to you',
  conflicting_policy:            'Your own rules disagreed here',
  unsupported_request:           'Agent had no rule for this'
};

async function refreshOrders(){
  const d = await api('/api/orders');
  $('#orderCount').textContent = d.total ? `${d.total} total · ${d.waiting} need you` : '';
  const dot = $('#orderDot');
  dot.classList.toggle('hidden', !d.waiting); dot.textContent = d.waiting || '';
  $('#orderList').innerHTML = d.orders.length ? d.orders.map(o => {
    const rows = Object.entries(o.slots).map(([k,v]) =>
      `<div class="orow"><span>${SLOT_LABEL[k]||k}</span><b>${esc(v)}</b></div>`).join('');
    const done = o.owner_status && o.owner_status !== 'Waiting for deposit';
    return `<div class="order ${o.needs_you?'alert':''} ${done?'done':''}">
      <div class="ohd">
        <div><b>${esc(o.customer)}</b> <span class="chan">${o.channel}</span></div>
        <span class="ostat ${done?'ok':(o.needs_you?'warn':'')}">${esc(o.owner_status || (o.escalation?'Needs you':'In progress'))}</span>
      </div>
      ${o.escalation ? `<div class="oesc">${esc(ESC_LABEL[o.escalation.reason]||o.escalation.reason)}<br>
         <span class="tiny">The agent did not answer this. It's waiting for you.</span></div>` : ''}
      ${rows ? `<div class="ogrid">${rows}</div>` : ''}
      ${done ? '' : (o.escalation
        ? `<div class="oreply">
             <input placeholder="Reply to ${esc(o.customer)}…" data-rcid="${esc(o.conversation_id)}">
             <button class="primary" data-send="${esc(o.conversation_id)}">Send reply</button>
           </div>
           <div class="oacts"><button data-cid="${esc(o.conversation_id)}" data-act="handled">Mark handled without replying</button></div>`
        : `<div class="oacts">
             <button class="primary" data-cid="${esc(o.conversation_id)}" data-act="deposit_received">Deposit received — confirm</button>
             <button data-cid="${esc(o.conversation_id)}" data-act="cancelled">Cancel</button>
           </div>`)}
    </div>`; }).join('')
    : '<div class="empty">No orders yet. Take one on the previous screen.</div>';
  $$('#orderList button[data-act]').forEach(b => b.onclick = async () => {
    await api('/api/orders/action', {conversation_id: b.dataset.cid, action: b.dataset.act});
    refreshOrders();
  });
  $$('#orderList button[data-send]').forEach(b => b.onclick = async () => {
    const cid = b.dataset.send;
    const box = document.querySelector(`#orderList input[data-rcid="${CSS.escape(cid)}"]`);
    const text = (box?.value || '').trim();
    if (!text) return box?.focus();
    b.disabled = true; b.textContent = 'Sending…';
    const r = await api('/api/orders/reply', {conversation_id: cid, text});
    if (r.error) { alert(r.error); b.disabled = false; b.textContent = 'Send reply'; return; }
    if (String(r.delivered).startsWith('failed') || r.delivered === 'no bot token configured')
      alert('Saved to the conversation, but not delivered: ' + r.delivered);
    refreshOrders();
  });
  $$('#orderList input[data-rcid]').forEach(i => i.onkeydown = e => {
    if (e.key === 'Enter') document.querySelector(`#orderList button[data-send="${CSS.escape(i.dataset.rcid)}"]`)?.click();
  });
  card();
}

// ── result card ───────────────────────────────────────────────────────
async function card(){
  const c = await api('/api/result-card');
  const d = c.discovered, o = c.owner_control, v = c.validation;
  const html = `
    <div class="hd">Input</div><b>${c.input.conversations}</b> conversations · <b>${c.input.messages}</b> messages
    <div class="hd">It worked out</div>
    <b>${d.stages}</b> steps in your process<br><b>${d.required_fields}</b> things it asks every customer<br>
    <b>${d.evidence_backed_rules}</b> rules learned from your messages<br><b>${d.unresolved_questions}</b> things it refused to guess
    ${d.mean_policy_confidence?`<br>mean confidence <b>${d.mean_policy_confidence}</b>`:''}
    <div class="hd">You approved</div>
    ${o.approved ? `approved v<b>${o.version}</b> · ${o.edits} edits<br>hash ${o.hash}` : 'awaiting approval'}
    <div class="hd">Checked</div>
    <b>${v.scenarios_passed}</b>/<b>${v.scenarios_total}</b> safety tests passed<br>
    <b>${v.conversations_handled}</b> live conversations · <b>${v.escalations}</b> escalated`;
  $('#resultCard').innerHTML = html;
  const r2 = $('#resultCard2'); if (r2) r2.innerHTML = html;
}

$('#resetBtn').onclick = async () => {
  await api('/api/reset');
  CAND = null; DISABLED = new Set();
  location.reload();
};

// Keep the live screen fresh while it's active — new Telegram turns land in
// the store from the bot process, not from this page.
setInterval(() => { if ($('#live').classList.contains('active')) refreshLive(); }, 4000);

// Rehydrate from the server so a refresh never lands on an empty screen.
async function boot(){
  await status(); card(); refreshOrders();
  const st = await api('/api/status');
  if (st.import.loaded) {
    const r = await api('/api/import');
    $('#importStats').className = 'stats';
    doRenderImport(r);
  }
  const c = await api('/api/candidate');
  if (c && !c.error) {
    CAND = c; renderReview(c); $('#extractBtn').disabled = false;
    markDone('import');
    if (st.approval) {
      $('#statusPill').textContent = 'switched on \u00b7 v' + st.approval.recipe_version;
      $('#statusPill').className = 'pill ok';
      $('#compileBtn').classList.remove('hidden');
      markDone('review');
    }
  }
  refreshLive();
}
boot();
