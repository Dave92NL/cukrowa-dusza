// Uruchamianie synchronizacji cen z telefonu.
//
// Dlaczego przez GitHuba, a nie wprost ze sklepow: ani api.ah.nl, ani
// baktotaal.nl nie wysylaja naglowkow CORS, wiec przegladarka nie moze ich
// wywolac. api.github.com wysyla (allow-origin: *), wiec aplikacja prosi
// GitHuba, zeby to on pobral ceny po swojej stronie i zapisal w repozytorium.
//
// TOKEN NIGDY NIE TRAFIA DO REPOZYTORIUM. Mieszka w IndexedDB tej przegladarki,
// czyli tylko na tym telefonie. Repo jest publiczne, wiec gdyby token w nim
// wyladowal, kazdy moglby uruchamiac akcje na cudzym koncie.

import { getSettings, putSettings } from './store.js';

const API = 'https://api.github.com';
const WORKFLOW = 'prices.yml';

/** Wykrywa wlasciciela i repozytorium z adresu GitHub Pages.
    Adres podajemy z zewnatrz, zeby dalo sie to przetestowac bez github.io. */
export function detectRepo(loc = location) {
  const m = String(loc.hostname || '').match(/^([\w-]+)\.github\.io$/i);
  if (!m) return null;
  const owner = m[1];
  const seg = String(loc.pathname || '').split('/').filter(Boolean)[0];
  // Strona uzytkownika (owner.github.io) mieszka w repo <owner>.github.io;
  // projekt (owner.github.io/nazwa) w repo <nazwa>.
  return { owner, repo: seg || `${owner}.github.io` };
}

export async function getConfig() {
  const s = await getSettings();
  const auto = detectRepo();
  return {
    owner: s.ghOwner || auto?.owner || '',
    repo: s.ghRepo || auto?.repo || '',
    token: s.ghToken || '',
    autoDetected: !s.ghOwner && !!auto,
  };
}

export function saveConfig({ owner, repo, token }) {
  const patch = {};
  if (owner !== undefined) patch.ghOwner = owner.trim();
  if (repo !== undefined) patch.ghRepo = repo.trim();
  if (token !== undefined) patch.ghToken = token.trim();
  return putSettings(patch);
}

export async function isConfigured() {
  const c = await getConfig();
  return !!(c.owner && c.repo && c.token);
}

async function call(path, { method = 'GET', token, body } = {}) {
  const res = await fetch(API + path, {
    method,
    headers: {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* nie JSON */ }
  if (!res.ok) {
    const msg = data?.message || `HTTP ${res.status}`;
    throw new Error(
      res.status === 401 ? 'Token odrzucony — sprawdź, czy nie wygasł.' :
      res.status === 403 ? 'Brak uprawnień. Token musi mieć „Actions: write” do tego repozytorium.' :
      res.status === 404 ? 'Nie znaleziono repozytorium albo workflow. Sprawdź nazwę właściciela i repo.' :
      msg);
  }
  return data;
}

/** Sprawdza, czy token dziala i widzi repozytorium. */
export async function testConnection() {
  const { owner, repo, token } = await getConfig();
  if (!owner || !repo) throw new Error('Podaj właściciela i nazwę repozytorium.');
  if (!token) throw new Error('Podaj token.');
  const r = await call(`/repos/${owner}/${repo}`, { token });
  return r.full_name;
}

/** Uruchamia workflow. `inputs` trafia 1:1 do workflow_dispatch. */
export async function dispatch(inputs = {}) {
  const { owner, repo, token } = await getConfig();
  if (!owner || !repo || !token) {
    throw new Error('Najpierw połącz aplikację z GitHubem w Ustawieniach.');
  }
  const clean = {};
  for (const [k, v] of Object.entries(inputs)) {
    if (v !== undefined && v !== null && String(v) !== '') clean[k] = String(v);
  }
  await call(`/repos/${owner}/${repo}/actions/workflows/${WORKFLOW}/dispatches`,
             { method: 'POST', token, body: { ref: 'main', inputs: clean } });
}

/**
 * Czeka, az nowe ceny dojada na strone. Nie odpytujemy API o status przebiegu,
 * tylko sam plik: miedzy commitem a publikacja na Pages mija jeszcze chwila,
 * a liczy sie moment, w ktorym aplikacja naprawde widzi nowa cene.
 */
export async function waitForPrices(predicate, { timeoutMs = 240000, stepMs = 8000,
                                                 onTick } = {}) {
  const started = Date.now();
  let tries = 0;
  while (Date.now() - started < timeoutMs) {
    await new Promise(r => setTimeout(r, stepMs));
    tries++;
    onTick?.(Math.round((Date.now() - started) / 1000));
    try {
      const res = await fetch(`./data/prices.json?t=${Date.now()}`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        if (predicate(data)) return data;
      }
    } catch { /* offline albo chwilowy blad Pages - probujemy dalej */ }
  }
  throw new Error('Minęły 4 minuty i nowa cena się nie pojawiła. '
                  + 'Sprawdź zakładkę Actions w GitHubie.');
}
