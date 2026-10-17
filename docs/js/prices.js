// Ladowanie katalogu i cen. Oba pliki leza w tym samym originie co aplikacja,
// wiec nie ma problemu CORS, ktory blokuje wolanie api.ah.nl wprost.

import { getOverrides } from './store.js';
import { sourceOf } from './calc.js';

const CATALOG_URL = './data/catalog.json';
const PRICES_URL = './data/prices.json';

async function loadJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/**
 * Zwraca { catalog, prices, overrides, error }.
 * Nawet gdy siec padnie, service worker podaje ostatnia wersje z cache -
 * lepiej liczyc na wczorajszych cenach z ostrzezeniem niz nie liczyc wcale.
 */
export async function load() {
  const overrides = await getOverrides().catch(() => ({}));
  try {
    const [catalogRaw, prices] = await Promise.all([loadJSON(CATALOG_URL), loadJSON(PRICES_URL)]);
    const catalog = {};
    for (const [k, v] of Object.entries(catalogRaw)) {
      if (!k.startsWith('_')) catalog[k] = v;
    }
    return { catalog, prices: applyOverrides(prices, overrides), overrides, error: null };
  } catch (e) {
    return { catalog: {}, prices: { products: {} }, overrides, error: e.message };
  }
}

/** Ceny wpisane recznie wygrywaja z synchronizacja i nie sa przez nia nadpisywane. */
function applyOverrides(prices, overrides) {
  if (!overrides || !Object.keys(overrides).length) return prices;
  const products = { ...(prices.products || {}) };
  for (const [key, cents] of Object.entries(overrides)) {
    products[key] = { ...(products[key] || {}), price: cents, bonusPrice: null,
                      bonusLabel: null, ok: true, overridden: true };
  }
  return { ...prices, products };
}

/** Lista skladnikow do ekranu "Skladniki", posortowana alfabetycznie. */
export function ingredientList(catalog, prices) {
  return Object.entries(catalog)
    .map(([key, cat]) => {
      const p = (prices.products || {})[key] || {};
      const src = sourceOf(cat);
      return {
        key,
        name: cat.name || key,
        pack: cat.pack,
        unit: cat.unit,
        source: src,
        manual: src === 'manual',
        url: p.url || cat.url || null,
        synced: src === 'manual' ? true : !!p.syncedAt,
        syncedAt: p.syncedAt || null,
        title: p.title || null,
        price: src === 'manual' ? (p.price ?? cat.price) : (p.price ?? null),
        bonusPrice: p.bonusPrice ?? null,
        bonusLabel: p.bonusLabel ?? null,
        bonusUntil: p.bonusUntil ?? null,
        overridden: !!p.overridden,
        ok: src === 'manual' ? true : p.ok !== false && p.price != null,
        warning: p.warning || null,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'pl'));
}
