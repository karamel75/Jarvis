// Cartes holographiques : météo, marchés, mails, agenda, liste, info, chiffre clé.
// Les clés de données sont celles envoyées par les outils Python (en français pour la météo et les marchés).

const MAX_CARDS = 2;
let lifetime = 14;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v, d = 2) => (typeof v === 'number' ? v.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }) : esc(v));

// icônes météo au trait, dessinées pour le style holographique
const ICONS = {
  sun: '<circle cx="24" cy="24" r="8"/><path d="M24 6v5M24 37v5M6 24h5M37 24h5M11.3 11.3l3.5 3.5M33.2 33.2l3.5 3.5M11.3 36.7l3.5-3.5M33.2 14.8l3.5-3.5"/>',
  cloud: '<path d="M14 36h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0 1 13z"/>',
  'cloud-sun': '<path d="M19 12a7 7 0 0 1 12 5M25 5v3M35 9l-2 2M38 19h-3"/><path d="M12 38h18a7 7 0 0 0 0-14 9.5 9.5 0 0 0-18 2.5A5.8 5.8 0 0 0 12 38z"/>',
  fog: '<path d="M14 24h20a7 7 0 0 0 0-14 10 10 0 0 0-19 3 5.5 5.5 0 0 0-1 11zM8 31h32M12 37h24M16 43h16"/>',
  drizzle: '<path d="M14 28h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0 1 13zM17 34l-1 3M25 34l-1 3M33 34l-1 3"/>',
  rain: '<path d="M14 28h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0 1 13zM17 33l-2 7M25 33l-2 7M33 33l-2 7"/>',
  snow: '<path d="M14 28h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0 1 13zM17 35v4M15 37h4M25 37v4M23 39h4M33 35v4M31 37h4"/>',
  storm: '<path d="M14 28h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0 1 13zM25 30l-4 7h6l-4 7"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 48 48">${ICONS[name] || ICONS.cloud}</svg>`;

const RENDER = {
  weather(c) {
    const n = c.maintenant || {};
    const days = (c.jours || []).slice(0, 5).map((d, i) => `
      <div class="wx-day" style="animation-delay:${.25 + i * .07}s">
        <div class="d">${esc(d.jour)}</div>${icon(d.icon)}
        <div class="t">${esc(d.max)}° <i>${esc(d.min)}°</i></div>
        <div class="p">${d.pluie_pct != null ? esc(d.pluie_pct) + ' %' : ''}</div>
      </div>`).join('');
    return `
      <div class="wx-now">${icon(n.icon)}
        <div><div class="wx-temp">${esc(n.temp)}<sup>°C</sup></div><div class="wx-sky">${esc(n.ciel)}</div></div>
      </div>
      <div class="wx-meta">
        <span>ressenti <b>${esc(n.ressenti)}°</b></span><span>humidité <b>${esc(n.humidite)} %</b></span>
        <span>vent <b>${esc(n.vent_kmh)} km/h</b></span><span>☀ <b>${esc(c.lever)}</b> → <b>${esc(c.coucher)}</b></span>
      </div>
      <div class="wx-days">${days}</div>`;
  },
  markets(c) {
    return `<div class="rows">${(c.rows || []).map((r, i) => {
      const v = Number(r.variation_pct), cls = v > 0 ? 'up' : v < 0 ? 'down' : '';
      const sign = v > 0 ? '▲ +' : v < 0 ? '▼ ' : '';
      return `<div class="row" style="animation-delay:${.2 + i * .05}s">
        <span class="l">${esc(r.nom)}</span>
        <span class="v">${num(r.cours)} <span class="${cls}">${sign}${num(v)} %</span></span></div>`;
    }).join('')}</div>`;
  },
  mail(c) {
    return `<div class="rows">${(c.items || []).slice(0, 6).map((m, i) => `
      <div class="row" style="animation-delay:${.2 + i * .06}s"><span class="dot ${m.unread ? 'on' : ''}"></span>
        <div style="min-width:0"><div class="from">${esc(m.from)}</div><div class="subj">${esc(m.subject)}</div></div></div>`).join('')
      || '<div class="lines"><p>Boîte de réception à jour.</p></div>'}</div>`;
  },
  list(c) {
    return `<div class="rows">${(c.items || []).slice(0, 8).map((it, i) => `
      <div class="row" style="animation-delay:${.2 + i * .05}s"><span class="l">${esc(it.label ?? it.nom ?? '')}</span>
        <span class="v">${esc(it.value ?? '')}</span></div>`).join('')}</div>`;
  },
  info(c) {
    return `<div class="lines">${(c.lines || []).filter(Boolean).slice(0, 6).map((l) => `<p>${esc(l)}</p>`).join('')}</div>`;
  },
  stat(c) {
    return `<div class="big">${esc(c.value)}</div><div class="cap">${esc(c.caption)}</div>`;
  },
};
RENDER.agenda = RENDER.list;
const TAGS = { weather: 'MÉTÉO', markets: 'MARCHÉS', mail: 'COURRIER', agenda: 'AGENDA', list: 'LISTE', info: 'INFO', stat: 'DONNÉE' };

export function setLifetime(s) { if (s > 0) lifetime = s; }

export function showCard(card) {
  const host = document.getElementById('cards');
  const kind = RENDER[card.kind] ? card.kind : 'info';
  const el = document.createElement('section');
  el.className = `card ${kind}`;
  const stamp = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  el.innerHTML = `
    <i class="corner c1"></i><i class="corner c2"></i><i class="corner c3"></i><i class="corner c4"></i>
    <header><h2>${esc(card.title || TAGS[kind])}</h2><span class="tag">${TAGS[kind] || ''} · ${stamp}</span></header>
    ${RENDER[kind](card)}
    <i class="bar" style="animation-duration:${lifetime}s"></i>`;
  host.prepend(el);
  while (host.children.length > MAX_CARDS) dismiss(host.lastElementChild, true);
  el._timer = setTimeout(() => dismiss(el), lifetime * 1000);
}

function dismiss(el, now = false) {
  if (!el || el._gone) return;
  el._gone = true; clearTimeout(el._timer);
  if (now) { el.remove(); return; }
  el.classList.add('out');
  el.addEventListener('animationend', () => el.remove(), { once: true });
}

export function clearCards() {
  for (const el of [...document.getElementById('cards').children]) dismiss(el);
}
