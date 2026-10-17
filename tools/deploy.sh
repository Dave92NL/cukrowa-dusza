#!/usr/bin/env bash
# Tworzy repozytorium, wypycha kod i wlacza GitHub Pages.
# Uruchom raz, po `gh auth login`.
#
#     bash tools/deploy.sh [nazwa-repo]
#
# Repozytorium musi byc PUBLICZNE: GitHub Pages na darmowym koncie nie dziala
# z prywatnych repo. Nic prywatnego tam nie trafia - receptury, stawka i marze
# mieszkaja w IndexedDB telefonu, a token GitHuba nigdy nie jest zapisywany
# w plikach.

set -euo pipefail

REPO="${1:-cukrowa-dusza}"
cd "$(dirname "$0")/.."

command -v gh >/dev/null || { echo "Brak gh. Zainstaluj GitHub CLI i uruchom 'gh auth login'."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh nie jest zalogowany. Uruchom: gh auth login"; exit 1; }

OWNER=$(gh api user --jq .login)
echo "Konto:        $OWNER"
echo "Repozytorium: $OWNER/$REPO (publiczne)"
echo ""

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "Repozytorium juz istnieje - tylko wypycham zmiany."
else
  gh repo create "$REPO" --public \
    --description "Kalkulator kosztu tortow z cen Albert Heijn i Baktotaal" \
    --disable-wiki
  echo "Utworzone."
fi

git remote get-url origin >/dev/null 2>&1 || \
  git remote add origin "https://github.com/$OWNER/$REPO.git"
git branch -M main
git push -u origin main
echo "Kod wypchniety."

# Pages z galezi main, katalog /docs - kazdy push jest live po ~30 s,
# bez zadnego dodatkowego workflow.
echo ""
echo "Wlaczam GitHub Pages..."
gh api -X POST "repos/$OWNER/$REPO/pages" \
  -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
  || gh api -X PUT "repos/$OWNER/$REPO/pages" \
       -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
  || echo "  (nie udalo sie przez API - wlacz recznie: Settings > Pages > main /docs)"

echo ""
echo "──────────────────────────────────────────────"
echo "Adres aplikacji:  https://$OWNER.github.io/$REPO/"
echo "Pierwsze wdrozenie trwa 1-2 minuty."
echo ""
echo "Zostalo jeszcze:"
echo "  1. Token Apify:   gh secret set APIFY_TOKEN --repo $OWNER/$REPO"
echo "     (wklejasz sam, nie pojawi sie na ekranie ani w logach)"
echo "  2. Na iPhonie otworz adres w Safari i dodaj do ekranu domowego"
echo "──────────────────────────────────────────────"
