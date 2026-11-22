#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
BIN_DIR="${HOME}/.local/bin"

echo "Instalando ResoNexuz en $DIR..."
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -e "$DIR[audio]"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/resonexuz" <<EOF
#!/usr/bin/env bash
if [[ "\${1:-}" == "--wallpaper" ]] && [[ -f /usr/lib/libgtk4-layer-shell.so ]]; then
  export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so\${LD_PRELOAD:+:\$LD_PRELOAD}"
fi
exec "$VENV/bin/python" -m resonexuz "\$@"
EOF
chmod +x "$BIN_DIR/resonexuz"

echo ""
echo "Listo. Ejecuta:"
echo "  resonexuz --windowed --with-ui   # visualizador + configurador web"
echo "  resonexuz --ui                   # solo configurador web"
echo "  resonexuz --wallpaper            # fondo animado (Wayland)"
