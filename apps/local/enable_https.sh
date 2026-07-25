#!/bin/bash
# 録音（マイク）を使うにはHTTPSが必要。証明書を用意してサーバーをHTTPS化する。
#
# 方式A（推奨・Tailscale導入済みの場合）: 正式な証明書。警告なしでスマホからも使える
#   tailscale cert <マシン名>.<tailnet名>.ts.net
# 方式B: 自己署名証明書（このスクリプト）。ブラウザで警告が出るが、許可すれば使える
set -e
cd "$(dirname "$0")"

if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
  DOMAIN=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['Self']['DNSName'].rstrip('.'))" 2>/dev/null || true)
  if [ -n "$DOMAIN" ]; then
    echo "Tailscaleを検出: $DOMAIN"
    echo "正式な証明書を取得します（初回は数秒かかります）..."
    if tailscale cert --cert-file cert.pem --key-file key.pem "$DOMAIN" 2>/dev/null; then
      echo "✅ 取得しました。アクセス先: https://$DOMAIN:8765"
      python3 - <<EOF
import json
c=json.load(open("config.json"))
c["server"]["certfile"]="cert.pem"; c["server"]["keyfile"]="key.pem"
json.dump(c, open("config.json","w"), ensure_ascii=False, indent=2)
print("config.json にHTTPS設定を追加しました")
EOF
      echo "サーバーを再起動してください: launchctl kickstart -k gui/\$(id -u)/com.englishlearningapp.server"
      exit 0
    fi
    echo "（tailscale cert が使えなかったため自己署名にフォールバックします）"
  fi
fi

echo "自己署名証明書を作成します（ブラウザで「詳細」→「アクセスする」で進めれば使えます）"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=$(hostname)" \
  -addext "subjectAltName=DNS:$(hostname),DNS:localhost,IP:127.0.0.1" 2>/dev/null
python3 - <<'EOF'
import json
c=json.load(open("config.json"))
c["server"]["certfile"]="cert.pem"; c["server"]["keyfile"]="key.pem"
json.dump(c, open("config.json","w"), ensure_ascii=False, indent=2)
print("config.json にHTTPS設定を追加しました")
EOF
echo "✅ 完了。https://$(hostname):8765 でアクセスしてください"
echo "サーバー再起動: launchctl kickstart -k gui/\$(id -u)/com.englishlearningapp.server"
