#!/usr/bin/env python3
"""Podsumowanie synchronizacji w formacie Markdown (GitHub Step Summary).

Wyciagniete z workflow do osobnego pliku, bo zagniezdzony heredoc w bloku YAML
to pulapka na bledy wciecia - a tutaj da sie to po prostu uruchomic i sprawdzic:

    python3 tools/summary.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PRICES = os.path.join(ROOT, "docs", "data", "prices.json")


def main():
    out = []
    try:
        with open(PRICES, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print("### Ceny Albert Heijn\n\nNie moge odczytac `prices.json`: %s" % e)
        return 1

    products = data.get("products", {})
    attention = {k: v for k, v in products.items() if v.get("ok") is False}
    bonus = {k: v for k, v in products.items() if v.get("bonusPrice")}

    out.append("### Ceny skladnikow")
    out.append("")
    out.append("Zsynchronizowano: **%s**" % (data.get("syncedAt") or "nigdy"))
    out.append("")
    out.append("| | liczba |")
    out.append("|---|---:|")
    ah = sum(1 for v in products.values() if v.get("source") == "ah")
    bt = sum(1 for v in products.values() if v.get("source") == "baktotaal")
    nigdy = sum(1 for v in products.values() if v.get("ok") is not False and not v.get("syncedAt"))
    out.append("| produkty | %d |" % len(products))
    out.append("| z Albert Heijn | %d |" % ah)
    out.append("| z Baktotaal | %d |" % bt)
    if nigdy:
        out.append("| nigdy nie pobrane | %d |" % nigdy)
    out.append("| w promocji Bonus | %d |" % len(bonus))
    out.append("| wymaga uwagi | %d |" % len(attention))

    if bonus:
        out.append("")
        out.append("**W promocji Bonus**")
        out.append("")
        out.append("| skladnik | cena | Bonus | |")
        out.append("|---|---:|---:|---|")
        for key, v in sorted(bonus.items()):
            out.append("| `%s` | %.2f | **%.2f** | %s |" % (
                key, v["price"] / 100, v["bonusPrice"] / 100, v.get("bonusLabel") or ""))

    if attention:
        out.append("")
        out.append("**Wymaga uwagi** — zachowano ostatnia znana cene, oznaczona jako nieswieza:")
        out.append("")
        for key, v in sorted(attention.items()):
            out.append("- `%s` — %s" % (key, v.get("warning") or "brak szczegolow"))

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
