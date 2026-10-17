// Spoiwo: stan, zdarzenia, zapis. Kalkulacja siedzi w calc.js, rysowanie w ui.js.

import { cakeCost, scaleRecipe, diameterFactor } from './calc.js';
import { fmt, fmtPlain, parseMoney, parseAmount } from './money.js';
import * as store from './store.js';
import { load as loadPrices, ingredientList } from './prices.js';
import {
  $, $$, bind, mountLines, updateCosts, renderBonusHint, renderCakeHeader,
  renderSync, renderIngredients, renderCakes, toast, showScreen, openSheet, closeSheets,
} from './ui.js';

const state = {
  catalog: {}, prices: { products: {} }, error: null,
  settings: { ...store.DEFAULT_SETTINGS },
  recipes: [], activeId: null, screen: 'kalk',
  editing: null, pricingKey: null,
};

const active = () => state.recipes.find(r => r.id === state.activeId) || null;

function calcFor(recipe) {
  return cakeCost(recipe, state.catalog, state.prices, state.settings,
                  { useBonus: state.settings.useBonus });
}

// ───────────────────── renderowanie ─────────────────────

function refreshCalculator({ remount = true } = {}) {
  const recipe = active();
  if (!recipe) return;
  const calc = calcFor(recipe);
  if (remount) mountLines(calc); else updateCosts(calc);
  renderBonusHint(calc, state.settings.useBonus);
  renderCakeHeader(recipe, calc);
  $('[data-act="toggle-bonus"]').setAttribute('aria-pressed', String(state.settings.useBonus));
}

function refreshCakes() {
  renderCakes(state.recipes.map(r => ({
    recipe: r, calc: calcFor(r), marginPct: state.settings.marginPct,
  })), state.activeId);
}

function refreshIngredients() {
  renderSync(state.prices, state.error);
  renderIngredients(ingredientList(state.catalog, state.prices));
}

function refreshAll({ remount = true } = {}) {
  refreshCalculator({ remount });
  refreshCakes();
  refreshIngredients();
}

// ───────────────────── zapis ─────────────────────

let saveTimer = null;
function saveActiveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const r = active();
    if (r) store.recipes.put(r).catch(() => toast('Nie udało się zapisać zmian.'));
  }, 400);
}
// Wyjscie z aplikacji nie moze zgubic ostatniego znaku.
function flushSave() {
  clearTimeout(saveTimer);
  const r = active();
  if (r) store.recipes.put(r).catch(() => {});
}
addEventListener('pagehide', flushSave);
document.addEventListener('visibilitychange', () => { if (document.hidden) flushSave(); });

// ───────────────────── nawigacja ─────────────────────

function go(screen) {
  state.screen = screen;
  showScreen(screen);
  if (screen === 'torty') refreshCakes();
  if (screen === 'skl') refreshIngredients();
  if (screen === 'kalk') refreshCalculator();
}

$$('[data-go]').forEach(b => b.addEventListener('click', () => go(b.dataset.go)));

// ───────────────────── gramatury ─────────────────────
// Reagujemy na 'input', nie na 'blur' - sprzezenie musi byc natychmiastowe.

bind('lines').addEventListener('input', e => {
  const input = e.target.closest('input[data-amount]');
  if (!input) return;
  const recipe = active();
  if (!recipe) return;
  const i = Number(input.dataset.amount);
  const v = parseAmount(input.value);
  recipe.lines[i].amount = v == null ? 0 : v;
  refreshCalculator({ remount: false });     // bez przebudowy: pole zachowuje fokus
  saveActiveSoon();
});

bind('lines').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.matches('input[data-amount]')) e.target.blur();
});

// Dlugie przytrzymanie wiersza usuwa skladnik z receptury.
bind('lines').addEventListener('contextmenu', e => {
  const row = e.target.closest('[data-line]');
  if (!row) return;
  e.preventDefault();
  removeLine(Number(row.dataset.line));
});

function removeLine(i) {
  const recipe = active();
  if (!recipe || !recipe.lines[i]) return;
  const [gone] = recipe.lines.splice(i, 1);
  store.recipes.put(recipe);
  refreshAll();
  toast(`Usunięto: ${state.catalog[gone.key]?.name || gone.key}`);
}

// ───────────────────── akcje ─────────────────────

const actions = {
  'back-to-cakes': () => go('torty'),

  'toggle-bonus': async () => {
    state.settings.useBonus = !state.settings.useBonus;
    await store.putSettings({ useBonus: state.settings.useBonus });
    refreshAll({ remount: true });
  },

  'add-line': () => {
    const recipe = active();
    if (!recipe) return;
    const used = new Set(recipe.lines.map(l => l.key));
    const free = ingredientList(state.catalog, state.prices).filter(i => !used.has(i.key));
    bind('addline-list').innerHTML = free.length
      ? free.map(i => `<button class="row tappable" data-add="${i.key}" type="button">
          <div class="main"><div class="t"><span class="nm">${i.name}</span></div>
          <div class="s">${i.pack} ${i.unit === 'szt' ? 'szt' : i.unit} · ${
            i.price != null ? fmt(i.price) : 'brak ceny'}</div></div></button>`).join('')
      : '<div class="empty"><h3>Wszystko już dodane</h3><p>Każdy składnik z katalogu jest w tej recepturze.</p></div>';
    openSheet('addLine');
  },

  'edit-recipe': () => {
    const r = active();
    if (!r) return;
    state.editing = r.id;
    $('[data-bind="recipe-sheet-title"]').textContent = 'Tort';
    $('#r-name').value = r.name || '';
    $('#r-diameter').value = r.diameter ?? '';
    $('#r-slices').value = r.slices ?? '';
    $('#r-hours').value = r.hours ?? '';
    $('#r-overhead').value = r.overhead != null ? fmtPlain(r.overhead) : '';
    $('#r-price').value = r.price != null ? fmtPlain(r.price) : '';
    $('#r-scale').value = '';
    openSheet('recipe');
  },

  'new-recipe': async () => {
    const rec = { id: store.newId(), name: '', diameter: 22, slices: 12,
                  hours: 1.5, overhead: 300, price: null, lines: [] };
    await store.recipes.put(rec);
    state.recipes.push(rec);
    state.activeId = rec.id;
    state.editing = rec.id;
    go('kalk');
    actions['edit-recipe']();
  },

  'save-recipe': async () => {
    const r = state.recipes.find(x => x.id === state.editing);
    if (!r) return closeSheets();
    r.name = $('#r-name').value.trim() || 'Bez nazwy';
    r.diameter = parseAmount($('#r-diameter').value) ?? r.diameter;
    r.slices = Math.max(1, Math.round(parseAmount($('#r-slices').value) ?? r.slices ?? 1));
    r.hours = parseAmount($('#r-hours').value) ?? 0;
    r.overhead = parseMoney($('#r-overhead').value) ?? 0;
    r.price = parseMoney($('#r-price').value);     // null = licz z marzy
    await store.recipes.put(r);
    closeSheets();
    refreshAll();
    toast('Zapisano.');
  },

  'scale-recipe': () => {
    const r = state.recipes.find(x => x.id === state.editing);
    const to = parseAmount($('#r-scale').value);
    if (!r || !to || to <= 0) return toast('Podaj nową średnicę w cm.');
    if (!r.diameter) return toast('Najpierw ustaw obecną średnicę.');
    const f = diameterFactor(r.diameter, to);
    const scaled = scaleRecipe(r, to);
    Object.assign(r, scaled);
    $('#r-diameter').value = r.diameter;
    $('#r-slices').value = r.slices;
    $('#r-scale').value = '';
    store.recipes.put(r);
    refreshAll();
    toast(`Przeskalowano ×${f.toFixed(2).replace('.', ',')} na Ø ${to} cm.`);
  },

  'delete-recipe': async () => {
    const r = state.recipes.find(x => x.id === state.editing);
    if (!r) return;
    if (!confirm(`Usunąć „${r.name || 'Bez nazwy'}”? Tego nie można cofnąć.`)) return;
    await store.recipes.remove(r.id);
    state.recipes = state.recipes.filter(x => x.id !== r.id);
    state.activeId = state.recipes[0]?.id ?? null;
    closeSheets();
    if (!state.activeId) { refreshCakes(); go('torty'); }
    else { refreshAll(); go('torty'); }
    toast('Usunięto tort.');
  },

  'help-ingredients': () => {
    toast('Ceny pobiera GitHub Actions raz na dobę i zapisuje w repozytorium. Aplikacja czyta gotowy plik.', 5000);
  },

  settings: () => {
    $('#s-rate').value = fmtPlain(state.settings.hourlyRate);
    $('#s-margin').value = String(Math.round(state.settings.marginPct * 100));
    $('#s-alert').value = String(Math.round(state.settings.marginAlert * 100));
    bind('app-synced').textContent = state.prices.syncedAt
      ? new Date(state.prices.syncedAt).toLocaleDateString('pl-PL')
      : 'nigdy';
    openSheet('settings');
  },

  'save-settings': async () => {
    const rate = parseMoney($('#s-rate').value);
    const margin = parseAmount($('#s-margin').value);
    const alert_ = parseAmount($('#s-alert').value);
    const next = {
      hourlyRate: rate ?? state.settings.hourlyRate,
      marginPct: margin != null ? margin / 100 : state.settings.marginPct,
      marginAlert: alert_ != null ? alert_ / 100 : state.settings.marginAlert,
    };
    Object.assign(state.settings, next);
    await store.putSettings(next);
    closeSheets();
    refreshAll();
    toast('Zapisano ustawienia.');
  },

  'save-price': async () => {
    const key = state.pricingKey;
    const cents = parseMoney($('#p-price').value);
    if (!key) return closeSheets();
    if (cents == null || cents <= 0) return toast('Podaj cenę opakowania, np. 2,79.');
    await store.setOverride(key, cents);
    await reloadPrices();
    closeSheets();
    refreshAll();
    toast(`${state.catalog[key]?.name || key}: ${fmt(cents)}`);
  },

  'clear-price': async () => {
    const key = state.pricingKey;
    if (!key) return closeSheets();
    if (state.catalog[key]?.manual) return toast('Ten produkt nie jest w Albert Heijn — cena musi być ręczna.');
    await store.setOverride(key, null);
    await reloadPrices();
    closeSheets();
    refreshAll();
    toast('Wrócono do ceny z Albert Heijn.');
  },

  export: async () => {
    const data = await store.exportAll();
    const name = `cukrowa-dusza-${new Date().toISOString().slice(0, 10)}.json`;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    // Na iPhonie share sheet pozwala zapisac do Plikow lub iCloud Drive.
    try {
      const file = new File([blob], name, { type: 'application/json' });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: 'Kopia — cukrowa dusza' });
        return;
      }
    } catch (e) {
      if (e.name === 'AbortError') return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  import: () => bind('import-input').click(),

  'close-sheet': () => { closeSheets(); state.editing = null; state.pricingKey = null; },
};

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-act]');
  if (btn) { actions[btn.dataset.act]?.(); return; }

  const add = e.target.closest('[data-add]');
  if (add) {
    const recipe = active();
    if (recipe) {
      // 100 g/ml to rozsadny start, ale 100 jajek juz nie.
      const unit = state.catalog[add.dataset.add]?.unit;
      recipe.lines.push({ key: add.dataset.add, amount: unit === 'szt' ? 1 : 100 });
      store.recipes.put(recipe);
      closeSheets();
      refreshAll();
      toast(`Dodano: ${state.catalog[add.dataset.add]?.name || add.dataset.add}`);
    }
    return;
  }

  const ing = e.target.closest('[data-ingredient]');
  if (ing) return openPriceSheet(ing.dataset.ingredient);

  const cake = e.target.closest('[data-recipe]');
  if (cake) {
    state.activeId = cake.dataset.recipe;
    go('kalk');
  }
});

function openPriceSheet(key) {
  const cat = state.catalog[key];
  if (!cat) return;
  const p = state.prices.products?.[key] || {};
  state.pricingKey = key;
  bind('price-sheet-title').textContent = cat.name;
  bind('price-sheet-pack').textContent = `${cat.pack} ${cat.unit === 'szt' ? 'szt' : cat.unit}`;
  $('#p-price').value = p.price != null ? fmtPlain(p.price) : '';
  bind('price-sheet-hint').textContent = cat.manual
    ? 'Produkt poza Albert Heijn — cenę prowadzisz sam, synchronizacja go nie dotyka.'
    : p.warning
      ? `Synchronizacja zgłasza: ${p.warning}`
      : 'Ręczna cena wygrywa z synchronizacją, dopóki jej nie usuniesz.';
  openSheet('price');
}

bind('import-input').addEventListener('change', async e => {
  const file = e.target.files?.[0];
  e.target.value = '';
  if (!file) return;
  try {
    const n = await store.importAll(JSON.parse(await file.text()));
    await boot({ keepScreen: true });
    toast(`Wczytano ${n} ${n === 1 ? 'recepturę' : 'receptury'}.`);
  } catch (err) {
    toast(`Nie udało się wczytać: ${err.message}`);
  }
});

// Escape zamyka arkusz - liczy sie na Macu w przegladarce.
addEventListener('keydown', e => {
  if (e.key === 'Escape') actions['close-sheet']();
});

// ───────────────────── start ─────────────────────

async function reloadPrices() {
  const r = await loadPrices();
  state.catalog = r.catalog;
  state.prices = r.prices;
  state.error = r.error;
}

async function boot({ keepScreen = false } = {}) {
  await reloadPrices();
  state.settings = await store.getSettings();
  state.recipes = await store.ensureSeed();
  if (!state.activeId || !state.recipes.some(r => r.id === state.activeId)) {
    state.activeId = state.recipes[0]?.id ?? null;
  }
  refreshAll();
  if (!keepScreen) go(state.recipes.length > 1 ? 'torty' : 'kalk');
  if (state.error) toast(`Nie wczytałem cen: ${state.error}`, 5000);
}

boot().catch(e => {
  document.body.innerHTML =
    `<div class="empty"><h3>Aplikacja nie wystartowała</h3><p>${e.message}</p></div>`;
});

store.requestPersistence().then(ok => {
  const el = bind('app-persist');
  if (el) el.textContent = ok ? 'tak' : 'nie — zrób kopię';
});

// ───────────────────── service worker ─────────────────────

if ('serviceWorker' in navigator) {
  addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('./sw.js');
      // Nowa wersja po pushu: przejmujemy ja od razu, zeby wdrozenia byly
      // faktycznie automatyczne i nikt nie zostal na starym kodzie.
      reg.addEventListener('updatefound', () => {
        const sw = reg.installing;
        sw?.addEventListener('statechange', () => {
          if (sw.state === 'installed' && navigator.serviceWorker.controller) {
            toast('Nowa wersja gotowa — odśwież.', 6000);
          }
        });
      });
      const res = await fetch('./sw.js', { cache: 'no-store' }).catch(() => null);
      if (res) reg.update().catch(() => {});
    } catch { /* bez offline, aplikacja dalej dziala */ }
  });
}

navigator.serviceWorker?.addEventListener?.('message', e => {
  if (e.data?.version) bind('app-version').textContent = e.data.version;
});
