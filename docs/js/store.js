// Receptury, stawka godzinowa i marze NIE opuszczaja telefonu.
// GitHub Pages na darmowym koncie wymaga publicznego repo, wiec wszystko,
// co prywatne, zostaje tutaj - w IndexedDB przegladarki.

const DB_NAME = 'tortownik';
const DB_VERSION = 1;

export const DEFAULT_SETTINGS = {
  hourlyRate: 1200,   // grosze za godzine (€ 12,00)
  marginPct: 0.35,
  marginAlert: 0.20,
  useBonus: true,
};

let dbPromise = null;

function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('recipes')) {
        db.createObjectStore('recipes', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('settings')) {
        db.createObjectStore('settings');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function tx(store, mode, fn) {
  return open().then(db => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const req = fn(t.objectStore(store));
    t.oncomplete = () => resolve(req ? req.result : undefined);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

export const recipes = {
  all:    ()   => tx('recipes', 'readonly',  s => s.getAll()),
  get:    id   => tx('recipes', 'readonly',  s => s.get(id)),
  put:    rec  => tx('recipes', 'readwrite', s => s.put(rec)),
  remove: id   => tx('recipes', 'readwrite', s => s.delete(id)),
};

export async function getSettings() {
  const stored = await tx('settings', 'readonly', s => s.get('main'));
  return { ...DEFAULT_SETTINGS, ...(stored || {}) };
}

export function putSettings(partial) {
  return getSettings().then(curr =>
    tx('settings', 'readwrite', s => s.put({ ...curr, ...partial }, 'main')));
}

/** Ceny produktow wpisane recznie (poza AH albo nadpisane). */
export async function getOverrides() {
  return (await tx('settings', 'readonly', s => s.get('overrides'))) || {};
}

export async function setOverride(key, cents) {
  const o = await getOverrides();
  if (cents == null) delete o[key]; else o[key] = cents;
  return tx('settings', 'readwrite', s => s.put(o, 'overrides'));
}

export function newId() {
  return 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

/**
 * Receptura startowa, zeby aplikacja otwierala sie w stanie roboczym,
 * a nie jako pusta skorupa. Dodawana tylko raz, przy pierwszym uruchomieniu.
 */
export const SEED_RECIPE = {
  name: 'Red Velvet',
  diameter: 22,
  slices: 12,
  hours: 2.5,
  overhead: 305,
  price: null,
  lines: [
    { key: 'maslo', amount: 180 },
    { key: 'cukier', amount: 300 },
    { key: 'maka', amount: 320 },
    { key: 'jajka', amount: 4 },
    { key: 'maslanka', amount: 240 },
    { key: 'kakao', amount: 25 },
    { key: 'mascarpone', amount: 500 },
    { key: 'smietana', amount: 200 },
    { key: 'cukier_puder', amount: 120 },
    { key: 'barwnik', amount: 8 },
  ],
};

export async function ensureSeed() {
  const all = await recipes.all();
  if (all.length) return all;
  const seeded = { ...SEED_RECIPE, id: newId(), seeded: true };
  await recipes.put(seeded);
  return [seeded];
}

/** Kopia zapasowa - jedyna droga, bo nic nie trafia do chmury. */
export async function exportAll() {
  const [recs, settings, overrides] = await Promise.all([
    recipes.all(), getSettings(), getOverrides(),
  ]);
  return { app: 'tortownik', version: 1, exportedAt: new Date().toISOString(),
           recipes: recs, settings, overrides };
}

export async function importAll(data) {
  if (!data || data.app !== 'tortownik' || !Array.isArray(data.recipes)) {
    throw new Error('To nie jest kopia zapasowa Tortownika.');
  }
  for (const r of data.recipes) {
    if (r && r.id && Array.isArray(r.lines)) await recipes.put(r);
  }
  if (data.settings) await putSettings(data.settings);
  if (data.overrides) {
    await tx('settings', 'readwrite', s => s.put(data.overrides, 'overrides'));
  }
  return data.recipes.length;
}

/** iOS nie usuwa danych aplikacji dodanej do ekranu domowego, ale prosimy wyraznie. */
export async function requestPersistence() {
  try {
    if (navigator.storage && navigator.storage.persist) {
      if (await navigator.storage.persisted()) return true;
      return await navigator.storage.persist();
    }
  } catch { /* nieobslugiwane - nie szkodzi */ }
  return false;
}
