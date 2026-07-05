#!/bin/bash
# First-time git push. Run this yourself on the Mac (needs your GitHub auth).
#
# Prerequisites (one of):
#   A) GitHub CLI:  brew install gh && gh auth login
#   B) Create an empty repo manually at https://github.com/new
#      (name: englishLearningApp, do NOT add README/.gitignore)
set -e
cd "$(dirname "$0")"

REPO_NAME="englishLearningApp"

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "Using GitHub CLI to create repo and push..."
  gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
else
  echo "GitHub CLI not available. Manual mode:"
  echo "1. Create an empty repo at https://github.com/new (name: $REPO_NAME)"
  read -r -p "2. Enter your GitHub username: " GH_USER
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
  git branch -M main
  git push -u origin main   # username + Personal Access Token when prompted
fi

echo "Done. Next pushes: just 'git push'."
