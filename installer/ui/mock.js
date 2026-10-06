// A stand-in for the exe's bridge, for looking at the page in a browser:
//   python -m http.server (in the repo root), then
//   /installer/ui/index.html?mock=selection|blocked|hardblock|installing|error|nosave|welcome|done
// It reads the real manifests and plays the events the core would send.
// Never embedded in the exe.
(async function () {
  'use strict';
  var mode = new URLSearchParams(location.search).get('mock') || 'selection';
  window.ipc = { postMessage: function (m) { console.log('ipc ->', m); } };

  var got = await Promise.all([
    fetch('../../manifests/stack.json').then(function (r) { return r.json(); }),
    fetch('../../manifests/operating-point.json').then(function (r) { return r.json(); })
  ]);
  var stack = got[0], op = got[1];
  var root = 'C:\\Users\\you\\AppData\\Local\\Crow', desktop = 'C:\\Users\\you\\Desktop';
  var packages = { crow: 612000000, engine: 49000000 };
  window.crow.init({
    stack: stack, op: op, packages: packages, root: root, root_label: '%LOCALAPPDATA%\\Crow',
    desktop: desktop, desktop_label: 'Desktop'
  });
  var ev = window.crow.event;

  var report = {
    type: 'preflight', os_64bit: true, gpu_name: 'NVIDIA GeForce RTX 5090', vram_mib: 32607, compute_cap: '12.0',
    ram_bytes: 68719476736, disk_free_bytes: 900e9, webview2: true, hard_block: null, blocked: []
  };

  // The plan the core would make (plan::plan's order: packages, Crow-wide files, models smallest first).
  function plan(points) {
    var jobs = [
      { id: 'crow-package', kind: 'CrowPackage', bytes: packages.crow, points: [] },
      { id: 'engine-package', kind: 'EnginePackage', bytes: packages.engine, points: [] }
    ];
    (stack.crow_files || []).slice().sort(function (a, b) { return a.bytes - b.bytes; }).forEach(function (f) {
      jobs.push({ id: f.id, kind: 'Whisper', bytes: f.bytes, points: [] });
    });
    var byId = {}, models = [];
    stack.files.forEach(function (f) { byId[f.id] = f; });
    var sel = stack.points.filter(function (p) { return points.indexOf(p.id) >= 0; });
    var ids = [];
    sel.forEach(function (p) { p.files.forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); }); });
    ids.forEach(function (id) {
      models.push({ id: id, kind: 'Model', bytes: byId[id].bytes,
        points: sel.filter(function (p) { return p.files.indexOf(id) >= 0; }).map(function (p) { return p.id; }) });
    });
    models.sort(function (a, b) { return a.bytes - b.bytes; });
    jobs = jobs.concat(models);
    var dl = jobs.reduce(function (s, j) { return s + j.bytes; }, 0);
    return { type: 'planned', jobs: jobs, derived: [], download_bytes: dl, disk_bytes: dl };
  }
  function verify(p, f) { p.jobs.filter(f).forEach(function (j) { ev({ type: 'file_verified', id: j.id }); }); }
  function step(name, status, detail) { ev({ type: 'step', name: name, status: status, detail: detail || '' }); }
  function frame() { return new Promise(function (r) { requestAnimationFrame(function () { setTimeout(r, 0); }); }); }
  async function install() { await frame(); document.querySelector('[data-act=install]').click(); }

  var points = ['flash-next', '27b'], p = plan(points);
  var notBig = function (j) { return j.id !== 'fn-cnq'; };

  switch (mode) {
    case 'selection':
      ev(report); break;
    case 'blocked':
      ev(Object.assign({}, report, { ram_bytes: 34359738368,
        blocked: [{ point: 'flash-next', reason: 'Needs 64 GB RAM. This machine has 32 GB.' }] }));
      break;
    case 'hardblock':
      ev(Object.assign({}, report, { gpu_name: 'NVIDIA GeForce RTX 4090', compute_cap: '8.9',
        hard_block: "Crow's engine needs an NVIDIA RTX 50 series card. This machine has an NVIDIA GeForce RTX 4090." }));
      break;
    case 'installing':
    case 'error':
    case 'nosave':
      ev(report); await install(); ev(p);
      verify(p, function (j) { return j.kind !== 'Model'; });
      step('crow', 'ok', 'Installed. Version 3.0.0.'); step('engine', 'ok', 'Installed. Version 0.9.0.');
      step('python', 'ok', 'Python 3.13.7 found.');
      verify(p, notBig);
      ev({ type: 'file_started', id: 'fn-cnq', from_byte: 0, total: 104727179972 });
      ev({ type: 'file_progress', id: 'fn-cnq', done: 30.4e9, total: 104727179972 });
      ev({ type: 'file_retry', id: 'fn-cnq', attempt: 1, reason: 'connection reset' });
      ev({ type: 'file_started', id: 'fn-cnq', from_byte: 30.4e9, total: 104727179972 });
      ev({ type: 'file_progress', id: 'fn-cnq', done: 41.2e9, total: 104727179972 });
      if (mode === 'error') {
        ev({ type: 'file_error', id: 'fn-cnq', retryable: false,
          message: '404 Not Found from huggingface.co. The file may have moved.' });
      }
      if (mode === 'nosave') {
        step('state', 'warning', 'Progress is not being saved to ' + root + '\\setup\\state.json: Access is denied. (os error 5)');
      }
      break;
    case 'welcome':
      ev(report); ev(p);
      verify(p, notBig);
      ev({ type: 'file_progress', id: 'fn-cnq', done: 41.2e9, total: 104727179972 });
      step('crow', 'ok', 'Done before.'); step('engine', 'ok', 'Done before.');
      break;
    case 'done':
      ev(report); await install(); ev(p);
      verify(p, function () { return true; });
      step('crow', 'ok', 'Installed. Version 3.0.0.'); step('engine', 'ok', 'Installed. Version 0.9.0.');
      step('python', 'ok', 'Python 3.13.7 found.'); step('check', 'ok', 'flash-next, 27b checked.');
      step('shortcuts', 'ok', 'Shortcuts written.');
      ev({ type: 'done', installed: points, shortcut: desktop + '\\Crow.lnk' });
      break;
  }
})();
