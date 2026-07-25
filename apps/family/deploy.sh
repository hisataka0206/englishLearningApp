#!/usr/bin/env bash
# 家族版のデプロイ補助（マイグレーション適用 + Edge Function デプロイ）
#
#   bash deploy.sh check     … 前提の確認だけ（何も変更しない）
#   bash deploy.sh db        … マイグレーション3本を適用
#   bash deploy.sh functions … Edge Function 3本をデプロイ
#   bash deploy.sh all       … db → functions
#
# ★ APIキーはこのスクリプトでは扱わない（シェル履歴に残さないため）。
#   README「2. Edge Function のデプロイ」の supabase secrets set を手で実行すること。
set -euo pipefail
cd "$(dirname "$0")"          # ← apps/family へ移動。CLIは supabase/ を cwd から探す

FUNCS=(translate keywords assess)
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
ng()   { printf "  \033[31m✗\033[0m %s\n" "$1"; }
info() { printf "\n\033[1m%s\033[0m\n" "$1"; }

check() {
  local fail=0
  info "前提の確認"

  if command -v supabase >/dev/null 2>&1; then
    ok "supabase CLI: $(supabase --version 2>/dev/null | head -1)"
  else
    ng "supabase CLI が無い → npm i -g supabase"; fail=1
  fi

  [ -f supabase/config.toml ] && ok "supabase/config.toml あり" \
    || { ng "supabase/config.toml が無い"; fail=1; }

  local n=0
  for m in supabase/migrations/*.sql; do [ -f "$m" ] && n=$((n+1)); done
  [ "$n" -eq 3 ] && ok "マイグレーション 3本" || { ng "マイグレーションが $n 本（3本のはず）"; fail=1; }

  for f in "${FUNCS[@]}"; do
    [ -f "supabase/functions/$f/index.ts" ] && ok "関数 $f" || { ng "関数 $f が無い"; fail=1; }
  done
  [ -f supabase/functions/_shared/common.ts ] && ok "共有モジュール _shared/common.ts" \
    || { ng "_shared/common.ts が無い"; fail=1; }

  if [ -f supabase/.temp/project-ref ]; then
    ok "リンク済み: $(cat supabase/.temp/project-ref)"
  else
    ng "未リンク → supabase login && supabase link --project-ref <ref>"; fail=1
  fi

  if grep -q "YOUR-PROJECT" web/config.js 2>/dev/null; then
    ng "web/config.js が未設定（プレースホルダのまま）"; fail=1
  else
    ok "web/config.js 設定済み"
  fi

  echo
  [ "$fail" -eq 0 ] && echo "→ 準備OK。 bash deploy.sh all" || echo "→ 上の ✗ を解消してから再実行"
  return "$fail"
}

db() {
  info "マイグレーションの適用（supabase db push）"
  supabase db push
  ok "適用完了。ping() が入ったか確認: select public.ping();"
}

functions_() {
  info "Edge Function のデプロイ"
  for f in "${FUNCS[@]}"; do
    echo "--- $f"
    supabase functions deploy "$f"
  done
  ok "3本ともデプロイ完了"
  echo
  echo "確認: supabase secrets list  （GEMINI_API_KEY / AZURE_SPEECH_KEY 等があるか）"
}

case "${1:-check}" in
  check) check ;;
  db) db ;;
  functions) functions_ ;;
  all) db; functions_ ;;
  *) echo "使い方: bash deploy.sh [check|db|functions|all]"; exit 1 ;;
esac
