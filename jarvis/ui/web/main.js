// Chef d'orchestre de la page : WebSocket vers Python, globe, cartes, saisie clavier, mode démo.
import { Globe } from './globe.js';
import { showCard, clearCards, setLifetime } from './cards.js';

const demo = new URLSearchParams(location.search).has('demo');
const globe = new Globe(document.getElementById('globe'));
const typer = document.getElementById('typer');
const input = document.getElementById('typer-input');
let ws = null;

function setVisible(on) {
  document.body.classList.toggle('vanished', !on);
  if (on) globe.appear();
  else { globe.vanish(); clearCards(); }
}

function handle(msg) {
  switch (msg.t) {
    case 'hello':
      setLifetime(msg.card_seconds);
      globe.setState(msg.state);
      if (msg.visible) setVisible(true);
      break;
    case 'state': globe.setState(msg.v); if (msg.v !== 'speak') globe.setLevel(0); break;
    case 'level': globe.setLevel(msg.v, msg.bands); break;
    case 'mic': globe.setMic(msg.v); break;
    case 'card': showCard(msg); break;
    case 'show': setVisible(true); break;
    case 'hide': setVisible(false); break;
  }
}

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  ws.onclose = () => setTimeout(connect, 1000);  // Python redémarre ? on se reconnecte seul
}
if (location.protocol.startsWith('http')) connect();

// « / » : écrire à Jarvis quand parler n'est pas possible
addEventListener('keydown', (e) => {
  if (e.target === input) {
    if (e.key === 'Escape') { typer.hidden = true; input.blur(); }
    return;
  }
  if (e.key === '/') { e.preventDefault(); typer.hidden = false; input.focus(); return; }
  if (demo) demoKey(e.key.toLowerCase());
});
typer.addEventListener('submit', (e) => {
  e.preventDefault();
  const v = input.value.trim();
  if (v && ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'text', v }));
  input.value = ''; typer.hidden = true; input.blur();
});

// ── mode démo (jarvis preview / ?demo) : voir le globe sans micro ni clé ──
const SAMPLES = {
  w: { kind: 'weather', title: 'Paris', ville: 'Paris', lever: '08:04', coucher: '19:12',
       maintenant: { temp: 17, ressenti: 16, humidite: 62, vent_kmh: 14, ciel: 'partiellement nuageux', icon: 'cloud-sun' },
       jours: [{ jour: 'auj.', min: 11, max: 18, pluie_pct: 10, icon: 'cloud-sun' }, { jour: 'dim', min: 12, max: 19, pluie_pct: 5, icon: 'sun' },
               { jour: 'lun', min: 10, max: 15, pluie_pct: 70, icon: 'rain' }, { jour: 'mar', min: 9, max: 14, pluie_pct: 40, icon: 'drizzle' }] },
  m: { kind: 'markets', title: 'Marchés', rows: [
       { nom: 'CAC 40', cours: 8124.31, variation_pct: 0.84 }, { nom: 'S&P 500', cours: 6702.1, variation_pct: 0.31 },
       { nom: 'Nasdaq', cours: 22841.6, variation_pct: -0.42 }, { nom: 'Bitcoin', cours: 118250, variation_pct: 2.15 },
       { nom: 'Euro / Dollar', cours: 1.1642, variation_pct: -0.08 }, { nom: 'Or', cours: 3984.2, variation_pct: 0.56 }] },
  e: { kind: 'mail', title: 'Outlook', items: [
       { from: 'Exemple · Banque', subject: 'Votre relevé de septembre est disponible', unread: true },
       { from: 'Exemple · Léa', subject: 'Dîner samedi ?', unread: true },
       { from: 'Exemple · SNCF', subject: 'Votre billet Paris → Lyon', unread: false }] },
  a: { kind: 'agenda', title: 'Agenda', items: [{ label: 'Salle de sport', value: '10-11 07:30' }, { label: 'Dîner chez Léa', value: '10-11 20:00' }] },
  s: { kind: 'stat', title: 'Distance', value: '384 400 km', caption: 'Terre → Lune' },
  i: { kind: 'info', title: 'En lecture', lines: ['Get Lucky', 'Daft Punk', 'Random Access Memories'] },
};
let fake = null;
function demoKey(k) {
  const states = { 1: 'idle', 2: 'listen', 3: 'think', 4: 'speak' };
  if (states[k]) {
    globe.setState(states[k]);
    clearInterval(fake); globe.setLevel(0); globe.setMic(0);
    if (k === '4') fake = setInterval(() => {      // voix simulée : syllabes et respirations
      const t = performance.now() / 1000, env = Math.max(0, Math.sin(t * 9) * Math.sin(t * 2.3 + 1)) ** .7;
      globe.setLevel(env * .8, Array.from({ length: 24 }, (_, i) => env * Math.max(0, Math.sin(i * .5 + t * 7) * .6 + .3) * (1 - i / 30)));
    }, 33);
    if (k === '2') fake = setInterval(() => globe.setMic(Math.max(0, Math.sin(performance.now() / 160)) * .6 * Math.random()), 50);
  } else if (k === 'h') setVisible(!globe.visible);
  else if (SAMPLES[k]) showCard(SAMPLES[k]);
}
if (demo) {
  document.body.classList.add('demo');
  document.getElementById('demo-help').hidden = false;
  setVisible(true);
  const q = new URLSearchParams(location.search);    // captures d'écran : ?demo&instant&state=4&card=w
  if (q.has('instant')) { globe.form = 1; globe.shock.forEach((s) => (s.t = 9)); }
  if (q.get('state')) demoKey(q.get('state'));
  for (const c of (q.get('card') || '').split('')) if (SAMPLES[c]) showCard(SAMPLES[c]);
}
