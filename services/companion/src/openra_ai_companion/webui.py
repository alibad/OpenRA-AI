AI_CONSOLE_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>OpenRA AI — Companion Console</title>
  <style>
    :root { color-scheme: dark; --bg:#0b0d0b; --panel:#141814; --line:#303a30; --text:#eef2e8; --muted:#98a294; --green:#9ee66f; --gold:#e7c85e; --red:#ff735f; }
    * { box-sizing:border-box; } body { margin:0; background:radial-gradient(circle at 80% 0,#1d291b 0,transparent 35%),var(--bg); color:var(--text); font:15px/1.45 system-ui,sans-serif; }
    main { width:min(1060px,calc(100% - 32px)); margin:0 auto; padding:38px 0 70px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:26px; }
    .eyebrow { color:var(--green); font:700 12px/1.2 ui-monospace,monospace; letter-spacing:.13em; text-transform:uppercase; }
    h1 { margin:8px 0 5px; font-size:clamp(28px,5vw,52px); letter-spacing:-.04em; } p { color:var(--muted); margin:0; }
    .status { display:flex; align-items:center; gap:8px; border:1px solid var(--line); background:#101310; padding:10px 13px; border-radius:999px; white-space:nowrap; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--gold); box-shadow:0 0 14px currentColor; } .ok .dot{background:var(--green)} .bad .dot{background:var(--red)}
    .grid { display:grid; grid-template-columns:1.15fr .85fr; gap:18px; } .panel { border:1px solid var(--line); background:color-mix(in srgb,var(--panel) 94%,transparent); border-radius:14px; padding:22px; }
    h2 { margin:0 0 4px; font-size:18px; } .sub { margin-bottom:19px; font-size:13px; }
    label { display:block; color:#bcc6b7; font:700 11px/1.2 ui-monospace,monospace; letter-spacing:.08em; text-transform:uppercase; margin:14px 0 6px; }
    input { width:100%; height:42px; border:1px solid var(--line); border-radius:7px; background:#0d100d; color:var(--text); padding:0 12px; outline:none; } input:focus { border-color:var(--green); }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    button,a.button { border:1px solid #465345; border-radius:7px; background:#1d241c; color:var(--text); min-height:40px; padding:0 13px; font-weight:700; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; text-decoration:none; }
    button:hover,a.button:hover { border-color:var(--green); } button.primary { background:var(--green); color:#10150e; border-color:var(--green); }
    .actions { display:flex; flex-wrap:wrap; gap:9px; margin-top:18px; } .tests { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:18px; }
    pre { min-height:190px; max-height:330px; overflow:auto; white-space:pre-wrap; border:1px solid #273027; background:#090b09; border-radius:8px; padding:14px; color:#cbd6c6; font:12px/1.55 ui-monospace,monospace; }
    .note { border-left:2px solid var(--gold); padding-left:12px; margin-top:18px; font-size:13px; }
    @media(max-width:760px){.grid{grid-template-columns:1fr}.row{grid-template-columns:1fr}header{display:block}.status{margin-top:18px;width:max-content}.tests{grid-template-columns:1fr}}
  </style>
</head>
<body><main>
  <header><div><div class="eyebrow">OpenRA AI / local control plane</div><h1>Companion Console</h1><p>Configure the AI layer and verify every model route before entering a match.</p></div><div id="status" class="status"><i class="dot"></i><span>Checking AI layer…</span></div></header>
  <div class="grid">
    <section class="panel"><h2>AI layer routing</h2><p class="sub">Provider credentials stay in the AI layer. OpenRA stores only local route names.</p>
      <label for="router_url">AI Layer URL</label><input id="router_url" autocomplete="off">
      <div class="row"><div><label for="text_model">Companion model</label><input id="text_model"></div><div><label for="transcribe_model">Transcription route</label><input id="transcribe_model"></div></div>
      <div class="row"><div><label for="speech_model">Speech route</label><input id="speech_model"></div><div><label for="speech_voice">Voice</label><input id="speech_voice"></div></div>
      <label for="timeout_seconds">Request timeout (seconds)</label><input id="timeout_seconds" type="number" min="1" max="120">
      <div class="actions"><button class="primary" id="save">Save configuration</button><button id="reload">Reload</button><a class="button" href="http://127.0.0.1:8788/">Earth Mission Studio</a></div>
      <p class="note">Saved locally under your user profile. API keys are never accepted or displayed here.</p>
    </section>
    <section class="panel"><h2>End-to-end diagnostics</h2><p class="sub">Tests use the same routes and audio path as live gameplay.</p>
      <div class="tests"><button data-test="connection">1. Connection</button><button data-test="chat">2. Text model</button><button data-test="microphone">3. Microphone</button><button data-test="speech">4. Speech</button></div>
      <div class="actions"><button class="primary" data-test="full">Run full AI test</button></div>
      <label>Diagnostic output</label><pre id="log">Ready.</pre>
    </section>
  </div>
</main><script>
const fields=['router_url','text_model','transcribe_model','speech_model','speech_voice','timeout_seconds'];
const log=document.querySelector('#log'), status=document.querySelector('#status');
function write(value){log.textContent=typeof value==='string'?value:JSON.stringify(value,null,2)}
async function request(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const data=await response.json();if(!response.ok)throw new Error(data.detail||data.error||`HTTP ${response.status}`);return data}
async function load(){try{const cfg=await request('/v1/config');fields.forEach(k=>document.querySelector('#'+k).value=cfg[k]);const health=await request('/health');const reachable=!!health.router?.reachable;status.className='status '+(reachable?'ok':'bad');status.querySelector('span').textContent=reachable?'AI layer online':'AI layer unavailable'}catch(error){status.className='status bad';status.querySelector('span').textContent='Control plane unavailable';write(error.message)}}
document.querySelector('#save').onclick=async()=>{try{const body=Object.fromEntries(fields.map(k=>[k,document.querySelector('#'+k).value]));write(await request('/v1/config',{method:'POST',body:JSON.stringify(body)}));await load()}catch(error){write('Save failed: '+error.message)}};
document.querySelector('#reload').onclick=load;
document.querySelectorAll('[data-test]').forEach(button=>button.onclick=async()=>{const test=button.dataset.test;button.disabled=true;write(test==='microphone'?'Listening for 3 seconds — speak now…':`Running ${test} test…`);try{write(await request('/v1/test/'+test,{method:'POST',body:'{}'}));await load()}catch(error){write(`${test} failed: ${error.message}`)}finally{button.disabled=false}});
load();
</script></body></html>"""
