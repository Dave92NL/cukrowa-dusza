// Pieniądze trzymamy wyłącznie w groszach jako liczby całkowite.
// Floaty na kwotach dryfują, a tu sumujemy dziesiątki pozycji.

/** Grosze -> "€ 12,34" */
export function fmt(c) {
  const v = Math.round(c) / 100;
  return '€ ' + v.toFixed(2).replace('.', ',');
}

/** Grosze -> "12,34" (bez symbolu) */
export function fmtPlain(c) {
  return (Math.round(c) / 100).toFixed(2).replace('.', ',');
}

/** "2,79" | "2.79" | 2.79 -> 279 grosze. Zwraca null gdy nie da się odczytać. */
export function parseMoney(input) {
  if (typeof input === 'number') return Number.isFinite(input) ? Math.round(input * 100) : null;
  if (typeof input !== 'string') return null;
  const s = input.replace(/[^\d,.-]/g, '').replace(',', '.');
  if (s === '' || s === '-' || s === '.') return null;
  const n = parseFloat(s);
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

/** "180" | "1,5" -> liczba. Zwraca null gdy nie da się odczytać. */
export function parseAmount(input) {
  if (typeof input === 'number') return Number.isFinite(input) ? input : null;
  if (typeof input !== 'string') return null;
  const s = input.replace(/[^\d,.-]/g, '').replace(',', '.');
  if (s === '' || s === '-' || s === '.') return null;
  const n = parseFloat(s);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** Cena za 1000 g/ml, do pokazania jako €/kg lub €/l. */
export function per1000(unitPriceCents) {
  return unitPriceCents * 1000;
}
