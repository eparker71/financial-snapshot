#!/usr/bin/env bash
# Publish html/ to the gh-pages branch (served by GitHub Pages).
# Uses a git worktree in .pages/ so the main working tree is untouched.
set -euo pipefail
cd "$(dirname "$0")"

# Custom domain is opt-in: set PAGES_CNAME=mktpulse.online once DNS points at GitHub Pages.
CNAME_DOMAIN="${PAGES_CNAME:-}"

if [ ! -d .pages ]; then
  git fetch origin gh-pages 2>/dev/null || true
  if git show-ref --verify --quiet refs/remotes/origin/gh-pages; then
    git worktree add -B gh-pages .pages origin/gh-pages
  else
    git worktree add --detach .pages
    git -C .pages checkout --orphan gh-pages
    git -C .pages rm -rf -q . || true
  fi
fi

rsync -a --delete --exclude '.git' --exclude CNAME html/ .pages/
if [ -n "$CNAME_DOMAIN" ]; then echo "$CNAME_DOMAIN" > .pages/CNAME; fi
touch .pages/.nojekyll

cd .pages
git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "publish $(date '+%Y-%m-%d %H:%M')"
elif [ -z "$(git log @{u}..HEAD --oneline 2>/dev/null)" ]; then
  echo "No changes to publish."
  exit 0
fi
# Also pushes any earlier local commits that never made it to the remote.
git push -u origin gh-pages
