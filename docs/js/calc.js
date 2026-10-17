// Serce aplikacji: czyste funkcje, zero DOM, zero zależności.
// Wszystkie kwoty w groszach. Stawki jednostkowe mogą być ułamkowe
// (grosze za 1 g to rzadko liczba całkowita) — zaokrąglamy dopiero na wyjściu.

export const UNITS = ['g', 'ml', 'szt'];

/** Czy promocja Bonus jest jeszcze aktualna danego dnia. */
export function bonusActive(product, today = new Date()) {
  if (!product || product.bonusPrice == null) return false;
  if (!product.bonusUntil) return true;           // brak daty = traktujemy jako aktywną
  const until = new Date(product.bonusUntil + 'T23:59:59');
  return Number.isFinite(until.getTime()) ? until >= today : true;
}

/**
 * Cena za jedną jednostkę bazową (1 g / 1 ml / 1 szt), w groszach.
 * Zwraca null, gdy produkt nie ma użytecznej ceny — wtedy wiersz jest "missing"
 * i NIE wolno go policzyć jako zero.
 */
export function unitPrice(product, { useBonus = true, today = new Date() } = {}) {
  if (!product || !product.pack || product.pack <= 0) return null;
  const useB = useBonus && bonusActive(product, today);
  const price = useB ? product.bonusPrice : product.price;
  if (price == null || !Number.isFinite(price)) return null;
  return price / product.pack;
}

/** Koszt jednej pozycji receptury w groszach (nieokrąglony). */
export function lineCost(amount, product, opts) {
  const up = unitPrice(product, opts);
  if (up == null || !Number.isFinite(amount) || amount < 0) return null;
  return up * amount;
}

/**
 * Scala wpis z katalogu z ceną z prices.json w jeden "produkt".
 * Katalog jest źródłem prawdy dla gramatury i jednostki — synchronizacja
 * aktualizuje wyłącznie cenę. Dzięki temu zmiana opakowania przez AH
 * (250 g -> 200 g) nie przechodzi po cichu.
 */
/** Zrodlo wpisu. Starsze katalogi uzywaly 'manual: true' zamiast 'source'. */
export function sourceOf(cat) {
  if (!cat) return 'missing';
  if (cat.source) return cat.source;
  return cat.manual ? 'manual' : 'ah';
}

export function resolveProduct(key, catalog, prices) {
  const cat = catalog && catalog[key];
  if (!cat) return null;
  const src = sourceOf(cat);
  const base = { key, name: cat.name, pack: cat.pack, unit: cat.unit, source: src };

  if (src === 'manual') {
    return { ...base, price: cat.price ?? null, bonusPrice: null, bonusUntil: null,
             ok: cat.price != null, synced: true };
  }
  const p = prices && prices.products && prices.products[key];
  if (!p) return { ...base, price: null, bonusPrice: null, ok: false, source: 'missing' };

  return { ...base,
    price: p.price ?? null,
    bonusPrice: p.bonusPrice ?? null,
    bonusUntil: p.bonusUntil ?? null,
    bonusLabel: p.bonusLabel ?? null,
    title: p.title ?? null,
    ean: p.ean ?? null,
    sku: p.sku ?? null,
    url: p.url ?? cat.url ?? null,
    // Cena bez wlasnego znacznika czasu nigdy nie byla pobrana - to wciaz
    // wartosc przykladowa i aplikacja musi to pokazac, a nie udawac swiezosc.
    synced: !!p.syncedAt,
    syncedAt: p.syncedAt ?? null,
    ok: p.ok !== false && p.price != null,
    warning: p.warning ?? null };
}

/**
 * Pełna kalkulacja tortu.
 *   recipe   { name, diameter, slices, hours, overhead, lines:[{key, amount}], price? }
 *   settings { hourlyRate, marginPct, marginAlert }
 * Zwraca kwoty w groszach; `ingredients` i `total` są nieokrąglone,
 * bo zaokrąglanie każdej pozycji osobno daje kilkucentowy błąd na 10 składnikach.
 */
export function cakeCost(recipe, catalog, prices, settings, opts = {}) {
  const o = { useBonus: true, today: new Date(), ...opts };

  const lines = (recipe.lines || []).map(l => {
    const product = resolveProduct(l.key, catalog, prices);
    const up = product ? unitPrice(product, o) : null;
    const base = product ? unitPrice(product, { ...o, useBonus: false }) : null;
    const cost = lineCost(l.amount, product, o);
    return {
      key: l.key,
      name: product ? product.name : l.key,
      amount: l.amount,
      unit: product ? product.unit : null,
      pack: product ? product.pack : null,
      unitPrice: up,
      baseUnitPrice: base,
      cost,
      bonus: product ? bonusActive(product, o.today) && o.useBonus : false,
      bonusLabel: product ? product.bonusLabel : null,
      source: product ? product.source : 'missing',
      synced: product ? product.synced !== false : false,
      ok: !!(product && product.ok && cost != null),
      warning: product ? product.warning : null,
      missing: cost == null,
    };
  });

  const ingredients = lines.reduce((s, l) => s + (l.cost ?? 0), 0);
  const ingredientsBase = lines.reduce(
    (s, l) => s + (l.baseUnitPrice != null && Number.isFinite(l.amount) ? l.baseUnitPrice * l.amount : 0), 0);

  const hours = Number.isFinite(recipe.hours) ? recipe.hours : 0;
  const rate = settings && Number.isFinite(settings.hourlyRate) ? settings.hourlyRate : 0;
  const labour = rate * hours;
  const overhead = Number.isFinite(recipe.overhead) ? recipe.overhead : 0;
  const total = ingredients + labour + overhead;

  const slices = Number.isFinite(recipe.slices) && recipe.slices > 0 ? recipe.slices : null;
  const marginPct = settings && Number.isFinite(settings.marginPct) ? settings.marginPct : 0;

  // Marża liczona od ceny sprzedaży, gdy cena jest ustawiona ręcznie.
  const actualMargin = (recipe.price != null && total > 0) ? (recipe.price - total) / total : null;

  return {
    lines,
    ingredients,
    bonusSavings: ingredientsBase - ingredients,
    labour, overhead, total,
    perSlice: slices ? total / slices : null,
    suggestedPrice: total * (1 + marginPct),
    pricePerSlice: slices ? (total * (1 + marginPct)) / slices : null,
    actualMargin,
    marginLow: actualMargin != null && settings && Number.isFinite(settings.marginAlert)
      ? actualMargin < settings.marginAlert : false,
    missing: lines.filter(l => l.missing).map(l => l.key),
    stale: lines.filter(l => !l.ok && !l.missing).map(l => l.key),
    unsynced: lines.filter(l => !l.synced && !l.missing && l.source !== 'manual').map(l => l.key),
    usedBonus: o.useBonus && lines.some(l => l.bonus),
  };
}

/**
 * Mnożnik przy zmianie średnicy. Liczy się POWIERZCHNIA blatu, nie średnica:
 * Ø22 -> Ø24 to ×1,19, a nie ×1,09. Pomyłka tutaj to 10% błędu w koszcie.
 */
export function diameterFactor(fromDiameter, toDiameter) {
  if (!fromDiameter || !toDiameter || fromDiameter <= 0) return 1;
  return (toDiameter / fromDiameter) ** 2;
}

/** Nowa receptura przeskalowana do innej średnicy. Gramatury zaokrąglane do 1. */
export function scaleRecipe(recipe, toDiameter) {
  const f = diameterFactor(recipe.diameter, toDiameter);
  return {
    ...recipe,
    diameter: toDiameter,
    slices: recipe.slices ? Math.round(recipe.slices * f) : recipe.slices,
    lines: (recipe.lines || []).map(l => ({ ...l, amount: Math.round(l.amount * f * 10) / 10 })),
  };
}

/** Ile dni ma plik z cenami. Null gdy brak znacznika. */
export function pricesAgeDays(prices, today = new Date()) {
  if (!prices || !prices.syncedAt) return null;
  const t = new Date(prices.syncedAt);
  if (!Number.isFinite(t.getTime())) return null;
  return (today - t) / 86400000;
}
