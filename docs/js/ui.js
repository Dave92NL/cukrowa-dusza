// Renderowanie. Zasada: wiersze buduje sie raz na zmiane receptury,
// a w trakcie pisania aktualizuje sie WYLACZNIE kwoty. Przebudowa listy
// przy kazdym znaku niszczy aktywne pole i zamyka klawiature na iPhonie.

import { fmt, fmtPlain } from './money.js';
import { pricesAgeDays } from './calc.js';

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const bind = name => document.querySelector(`[data-bind="${name}"]`);

const SVG_CHEV = '<svg width="8" height="13" viewBox="0 0 8 13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.2 1.2 6.5 6.5l-5.3 5.3"/></svg>';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const unitLabel = u => (u === 'szt' ? 'szt' : u);
const perLabel  = u => (u === 'szt' ? '/szt' : u === 'ml' ? '/l' : '/kg');

/** Cena za jednostke handlowa: €/kg, €/l albo €/szt. */
function perUnit(unitPrice, unit) {
  if (unitPrice == null) return '—';
  const v = unit === 'szt' ? unitPrice : unitPrice * 1000;
  return fmt(v) + perLabel(unit);
}

// ───────────────────── ekran: kalkulator ─────────────────────

/** Buduje wiersze skladnikow. Wolac tylko gdy zmienil sie SKLAD receptury. */
export function mountLines(calc) {
  const host = bind('lines');
  host.innerHTML = calc.lines.map((l, i) => `
    <div class="row" data-line="${i}">
      <div class="main">
        <div class="t"><span class="nm">${esc(l.name)}</span>${l.bonus ? '<span class="tag b">Bonus</span>' : ''}${
          l.source === 'manual' ? '<span class="tag">ręcznie</span>' : ''}${
          !l.ok && !l.missing ? '<span class="tag w">nieświeże</span>' : ''}</div>
        <div class="s" data-line-sub="${i}"></div>
      </div>
      <div class="amt">
        <input type="text" inputmode="decimal" enterkeyhint="done"
               value="${l.amount}" data-amount="${i}"
               aria-label="Zużycie: ${esc(l.name)}">
        <span class="u">${unitLabel(l.unit) || ''}</span>
      </div>
      <div class="cost" data-cost="${i}"></div>
    </div>`).join('') || `
    <div class="empty">
      <h3>Brak składników</h3>
      <p>Dotknij „Dodaj składnik”, żeby zacząć kalkulację.</p>
    </div>`;
  updateCosts(calc);
}

/** Aktualizuje tylko kwoty i podsumowanie. Nie rusza struktury ani pol. */
export function updateCosts(calc) {
  calc.lines.forEach((l, i) => {
    const sub = document.querySelector(`[data-line-sub="${i}"]`);
    if (sub) {
      sub.textContent = l.missing
        ? 'brak ceny — uzupełnij w Składnikach'
        : `${l.pack}${l.unit === 'szt' ? ' szt' : ' ' + l.unit} · ${perUnit(l.unitPrice, l.unit)}`;
    }
    const cell = document.querySelector(`[data-cost="${i}"]`);
    if (!cell) return;
    cell.classList.toggle('isBonus', !!l.bonus);
    cell.classList.toggle('isMissing', l.missing);
    if (l.missing) { clearNum(cell); cell.textContent = 'brak'; }
    else setNum(cell, l.cost);
  });
  renderSummary(calc);
}

export function renderSummary(calc) {
  const host = bind('summary');
  const pct = calc.actualMargin != null ? calc.actualMargin : null;
  const rows = [
    ['Składniki', calc.ingredients, ''],
    ['Robocizna', calc.labour, ''],
    ['Prąd + opakowanie', calc.overhead, ''],
  ];

  if (!host.dataset.built) {
    host.innerHTML = `
      ${rows.map((_, i) => `<div class="sline"><span class="k" data-sk="${i}"></span><span class="v" data-sv="${i}"></span></div>`).join('')}
      <div class="sline total"><span class="k">Koszt własny</span><span class="v" data-sv="total"></span></div>
      <div class="sline"><span class="k">Koszt 1 porcji</span><span class="v" data-sv="slice"></span></div>
      <div class="sline hero" data-hero><span class="k" data-sk="price"></span><span class="v" data-sv="price"></span></div>`;
    host.dataset.built = '1';
  }
  rows.forEach(([k, v], i) => {
    host.querySelector(`[data-sk="${i}"]`).textContent = k;
    setNum(host.querySelector(`[data-sv="${i}"]`), v);
  });
  setNum(host.querySelector('[data-sv="total"]'), calc.total);
  const slice = host.querySelector('[data-sv="slice"]');
  if (calc.perSlice == null) slice.textContent = '—'; else setNum(slice, calc.perSlice);

  const hero = host.querySelector('[data-hero]');
  const label = host.querySelector('[data-sk="price"]');
  const value = host.querySelector('[data-sv="price"]');
  if (pct != null) {
    label.textContent = 'Realna marża';
    clearNum(value);
    value.textContent = (pct * 100).toFixed(1).replace('.', ',') + '%';
    hero.classList.toggle('low', !!calc.marginLow);
  } else {
    label.textContent = 'Cena przy marży docelowej';
    hero.classList.remove('low');
    setNum(value, calc.suggestedPrice);
  }
}

export function renderBonusHint(calc, useBonus) {
  const el = bind('bonus-hint');
  const n = calc.lines.filter(l => l.bonusLabel || l.bonus).length;
  if (calc.bonusSavings > 0.5) {
    el.innerHTML = useBonus
      ? `${n} ${n === 1 ? 'składnik' : 'składniki'} w promocji Bonus — oszczędzasz <b>${fmt(calc.bonusSavings)}</b> na tym torcie.`
      : `Liczę ceny podstawowe. Włącz Bonus, żeby zbić koszt o <b>${fmt(calc.bonusSavings)}</b>.`;
  } else {
    el.textContent = 'Żaden ze składników nie jest teraz w promocji Bonus.';
  }

  const warn = bind('kalk-warn');
  const problems = [];
  if (calc.missing.length) problems.push(`Bez ceny: ${calc.missing.join(', ')} — te składniki NIE są doliczone.`);
  if (calc.stale.length) problems.push(`Nieświeże ceny: ${calc.stale.join(', ')} — sprawdź w Składnikach.`);
  warn.hidden = problems.length === 0;
  warn.textContent = problems.join(' ');
}

export function renderCakeHeader(recipe, calc) {
  bind('cake-name').textContent = recipe ? recipe.name || 'Bez nazwy' : '—';
  const parts = [];
  if (recipe?.diameter) parts.push(`Ø ${fmtPlain(recipe.diameter * 100).replace(',00', '')} cm`);
  if (recipe?.slices) parts.push(`${recipe.slices} porcji`);
  if (calc?.perSlice != null) parts.push(`${fmt(calc.perSlice)}/porcja`);
  bind('cake-sub').textContent = parts.join(' · ');
}

// ───────────────────── ekran: skladniki ─────────────────────

export function renderSync(prices, error) {
  const dot = bind('sync-dot'), title = bind('sync-title'), sub = bind('sync-sub');
  dot.className = 'dot';

  if (error) {
    dot.classList.add('bad');
    title.textContent = 'Nie udało się wczytać cen';
    sub.textContent = error;
    return;
  }
  if (prices.seed || !prices.syncedAt) {
    dot.classList.add('warn');
    title.textContent = 'Ceny przykładowe';
    sub.textContent = 'Uruchom synchronizację w GitHubie, żeby pobrać prawdziwe ceny.';
    return;
  }
  const age = pricesAgeDays(prices);
  const when = new Date(prices.syncedAt).toLocaleString('pl-PL',
    { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
  if (age != null && age > 2) {
    dot.classList.add('warn');
    title.textContent = `Ceny z ${Math.floor(age)} dni temu`;
    sub.textContent = `Ostatnia synchronizacja: ${when}. Sprawdź workflow w GitHubie.`;
  } else {
    title.textContent = 'Ceny aktualne';
    sub.textContent = `Zsynchronizowano ${when} · automatycznie, codziennie`;
  }
}

export function renderIngredients(list) {
  const host = bind('ingredients');
  const groups = [
    ['Z Albert Heijn', list.filter(i => !i.manual && !i.overridden)],
    ['Cena wpisana ręcznie', list.filter(i => i.manual || i.overridden)],
  ];
  host.innerHTML = groups.filter(([, items]) => items.length).map(([name, items]) => `
    <div class="ghead">${name} · ${items.length}</div>
    <div class="group">
      ${items.map(i => {
        const active = i.bonusPrice != null;
        const unitP = i.price != null ? perUnit((active ? i.bonusPrice : i.price) / i.pack, i.unit) : '—';
        const price = i.price == null ? 'brak ceny'
          : active ? `<span class="strike">${fmt(i.price)}</span> ${fmt(i.bonusPrice)}`
          : fmt(i.price);
        return `<button class="row tappable" data-ingredient="${esc(i.key)}" type="button">
          <div class="main">
            <div class="t"><span class="nm">${esc(i.name)}</span>${active ? `<span class="tag b">${esc(i.bonusLabel || 'Bonus')}</span>` : ''}${
              i.overridden ? '<span class="tag">ręcznie</span>' : ''}${
              !i.ok ? '<span class="tag w">sprawdź</span>' : ''}</div>
            <div class="s">${esc(i.title || '')}${i.title ? ' · ' : ''}${i.pack} ${unitLabel(i.unit)} · ${price} → ${unitP}</div>
          </div>
          <span class="chev">${SVG_CHEV}</span>
        </button>`;
      }).join('')}
    </div>`).join('');

  const bad = list.filter(i => !i.ok);
  bind('skl-sub').textContent = bad.length
    ? `${list.length} produktów · ${bad.length} wymaga uwagi`
    : `${list.length} produktów · ceny z Albert Heijn`;
}

// ───────────────────── ekran: torty ─────────────────────

const SWATCHES = [
  'linear-gradient(150deg,#C0304A,#8A1F33)', 'linear-gradient(150deg,#8C6239,#5A3C21)',
  'linear-gradient(150deg,#D9A42B,#A8761A)', 'linear-gradient(150deg,#6B8E5A,#44603A)',
  'linear-gradient(150deg,#4A6FA5,#2E4870)', 'linear-gradient(150deg,#8E5A86,#5E3858)',
];
const initials = name => (name || '?').split(/\s+/).slice(0, 2)
  .map(w => w[0] || '').join('').toUpperCase() || '?';

export function renderCakes(items, activeId) {
  const host = bind('cakes');
  if (!items.length) {
    host.innerHTML = `<div class="empty"><h3>Brak tortów</h3>
      <p>Dotknij „Nowy tort”, żeby dodać pierwszą recepturę.</p></div>`;
    bind('torty-sub').textContent = 'brak receptur';
    return;
  }

  host.innerHTML = `
    <div class="ghead">Receptury · ${items.length}</div>
    <div class="group">
      ${items.map((it, n) => {
        const c = it.calc;
        const margin = c.actualMargin != null
          ? `${c.actualMargin >= 0 ? '+' : ''}${(c.actualMargin * 100).toFixed(0)}% → ${fmt(it.recipe.price)}`
          : `cel +${Math.round((it.marginPct || 0) * 100)}% → ${fmt(c.suggestedPrice)}`;
        const problems = c.missing.length + c.stale.length;
        return `<button class="cake" data-recipe="${esc(it.recipe.id)}" type="button">
          <span class="swatch" style="background:${SWATCHES[n % SWATCHES.length]}">${esc(initials(it.recipe.name))}</span>
          <div class="main">
            <div class="t"><span class="nm">${esc(it.recipe.name || 'Bez nazwy')}</span>${
              it.recipe.id === activeId ? '<span class="tag g">otwarty</span>' : ''}${
              problems ? '<span class="tag w">sprawdź ceny</span>' : ''}</div>
            <div class="s">Ø ${it.recipe.diameter || '?'} cm · ${it.recipe.slices || '?'} porcji${
              c.perSlice != null ? ' · ' + fmt(c.perSlice) + '/porcja' : ''}</div>
          </div>
          <div class="right">
            <div class="p">${fmt(c.total)}</div>
            <div class="m ${c.marginLow ? 'low' : ''}">${margin}</div>
          </div>
        </button>`;
      }).join('')}
    </div>`;

  const low = items.filter(i => i.calc.marginLow).length;
  const avg = items.filter(i => i.calc.actualMargin != null);
  const avgTxt = avg.length
    ? ` · marża średnio ${Math.round(avg.reduce((s, i) => s + i.calc.actualMargin, 0) / avg.length * 100)}%`
    : '';
  bind('torty-sub').textContent =
    `${items.length} ${items.length === 1 ? 'receptura' : 'receptury'}${avgTxt}${low ? ` · ${low} pod progiem marży` : ''}`;
}

// ───────────────────── animacja liczb ─────────────────────
// Animacja jest OZDOBA, nigdy zrodlem prawdy. requestAnimationFrame bywa
// calkowicie wstrzymany (karta w tle, panel ukryty, oszczedzanie energii),
// wiec gdyby wartosc koncowa zalezala od klatek, uzytkownik zobaczylby kwote
// zamrozona w polowie drogi - czyli zla cene. Stad trzy zabezpieczenia:
// czas rzeczywisty zamiast licznika klatek, awaryjny setTimeout domykajacy
// wartosc i natychmiastowy skok, gdy dokument jest ukryty.

const DURATION = 380;
const tweens = new Map();                 // el -> stan, zeby dalo sie domknac wszystkie
const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const easeOut = t => 1 - Math.pow(1 - t, 3);

function commit(el, value) {
  el.textContent = fmt(value);
  const st = tweens.get(el);
  if (st) {
    if (st.raf) cancelAnimationFrame(st.raf);
    if (st.timer) clearTimeout(st.timer);
  }
  tweens.set(el, { cur: value });
}

export function setNum(el, to) {
  if (!el) return;
  if (to == null || !Number.isFinite(to)) {
    const st = tweens.get(el);
    if (st?.raf) cancelAnimationFrame(st.raf);
    if (st?.timer) clearTimeout(st.timer);
    tweens.delete(el);
    el.textContent = '—';
    return;
  }

  const prev = tweens.get(el);
  const from = prev ? prev.cur : to;

  if (reduceMotion() || document.hidden || Math.abs(to - from) < 0.5) {
    commit(el, to);
    return;
  }

  if (prev?.raf) cancelAnimationFrame(prev.raf);
  if (prev?.timer) clearTimeout(prev.timer);

  const t0 = performance.now();
  const st = { cur: from, from, to };
  tweens.set(el, st);

  const step = now => {
    const t = Math.min(1, (now - t0) / DURATION);
    st.cur = st.from + (st.to - st.from) * easeOut(t);
    el.textContent = fmt(st.cur);
    if (t < 1) st.raf = requestAnimationFrame(step);
    else commit(el, st.to);
  };
  st.raf = requestAnimationFrame(step);
  // Siatka bezpieczenstwa: nawet gdy rAF nigdy nie wystartuje, kwota ladnie
  // dojdzie do konca. setTimeout bywa spowolniony, ale sie wykonuje.
  st.timer = setTimeout(() => commit(el, st.to), DURATION + 120);
}

/** Przerywa animacje i zwalnia element - tekst ustawia wolajacy. */
export function clearNum(el) {
  const st = tweens.get(el);
  if (st?.raf) cancelAnimationFrame(st.raf);
  if (st?.timer) clearTimeout(st.timer);
  tweens.delete(el);
}

/** Natychmiast domyka wszystkie animacje. Wolane, gdy dokument znika z oczu. */
export function flushNumbers() {
  for (const [el, st] of tweens) if (st.to != null && st.cur !== st.to) commit(el, st.to);
}
document.addEventListener('visibilitychange', () => { if (document.hidden) flushNumbers(); });
addEventListener('pagehide', flushNumbers);

// ───────────────────── drobne ─────────────────────

let toastTimer = null;
export function toast(message, ms = 2600) {
  const el = bind('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

export function showScreen(name) {
  $$('[data-screen]').forEach(el => { el.hidden = el.dataset.screen !== name; });
  $$('[data-nav]').forEach(el => { el.hidden = el.dataset.nav !== name; });
  $$('[data-go]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.go === name)));
  window.scrollTo(0, 0);
}

export function openSheet(name) {
  $$('[data-sheet]').forEach(el => { el.hidden = el.dataset.sheet !== name; });
}
export function closeSheets() {
  $$('[data-sheet]').forEach(el => { el.hidden = true; });
}
