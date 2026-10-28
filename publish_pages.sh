#!/usr/bin/env bash
# Publish html/ to the gh-pages branch (served by GitHub Pages).
# Uses a git worktree in .pages/ so the main working tree is untouched.
set -euo pipefail
cd "$(dirname "$0")"

CNAME_DOMAIN="mktpulse.online"   # remove if not using a custom domain

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

rsync -a --delete --exclude '.git' html/ .pages/
[ -n "$CNAME_DOMAIN" ] && echo "$CNAME_DOMAIN" > .pages/CNAME
touch .pages/.nojekyll

cd .pages
git add -A
if git diff --cached --quiet; then
  echo "No changes to publish."
  exit 0
fi
git commit -q -m "publish $(date '+%Y-%m-%d %H:%M')"
git push -u origin gh-pages
