#!/bin/bash
# Publica una còpia netejada d'aquest repo (privat) al repo públic.
# Clona la branca, reescriu TOT l'historial amb git-filter-repo (substitucions
# i mailmap de ~/.config/entrenador-public, fora del repo perquè contenen el
# que s'amaga), comprova que no en queda res i fa push a main del públic.
# filter-repo és determinista: amb les mateixes regles, els commits antics
# surten amb el mateix hash i el push és un fast-forward. Si canvien les regles,
# l'historial canvia i cal --force.
#
# Ús: scripts/sync-public.sh [branca] [--force] [--dry-run]   (per defecte: main)
#     --dry-run: neteja i comprova, però no puja res
# Cal: brew install git-filter-repo
set -euo pipefail
REF=main; FORCE=(); DRY=0
for a in "$@"; do
  case "$a" in --force) FORCE=(--force) ;; --dry-run) DRY=1 ;; *) REF="$a" ;; esac
done
PRIVATE=https://github.com/roger-alles/entrenador-triatlo.git
PUBLIC=https://github.com/roger-alles/triathlon-coach.git
CONF="${ENTRENADOR_PUBLIC_CONF:-$HOME/.config/entrenador-public}"
[ -f "$CONF/replacements.txt" ] && [ -f "$CONF/mailmap" ] || { echo "falten regles a $CONF" >&2; exit 1; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
git clone -q --single-branch --branch "$REF" "$PRIVATE" "$work/repo"
cd "$work/repo"
git filter-repo --quiet --force \
  --replace-text "$CONF/replacements.txt" --replace-message "$CONF/replacements.txt" \
  --mailmap "$CONF/mailmap" \
  --invert-paths --path-glob '*.DS_Store' --path .claude/worktrees

# Comprovació: cap text literal de les regles (ni els noms d'abans) a cap blob,
# missatge o autor de l'historial.
patterns="$work/patterns"
grep -v '^regex:' "$CONF/replacements.txt" | sed 's/==>.*//' | grep -v '^github.com/' > "$patterns"
printf '%s\n' 'root té contrasenya' >> "$patterns"
sed -nE 's/.*<([^>]+)>$/\1/p' "$CONF/mailmap" >> "$patterns"
leaks=$( { git rev-list --objects HEAD | git cat-file --batch-check='%(objecttype) %(objectname)' \
             | awk '$1=="blob"{print $2}' | git cat-file --batch; git log --format='%an %ae %cn %ce%n%B' HEAD; } \
         | grep -aFc -f "$patterns" || true)
[ "$leaks" = "0" ] || { echo "ATURAT: $leaks línies encara contenen text que s'havia d'amagar" >&2; exit 1; }

[ $DRY = 1 ] && { echo "dry-run OK: $(git rev-list --count HEAD) commits nets, res pujat"; exit 0; }
git push "${FORCE[@]+"${FORCE[@]}"}" "$PUBLIC" HEAD:main
echo "Publicat $REF → $PUBLIC ($(git rev-list --count HEAD) commits)"
