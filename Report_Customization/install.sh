#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Zabbix HTML Reporter — Install Script
#
# Usage:  sudo bash install.sh [--install-dir /opt/zabbix-html-reporter]
#
# What it does:
#   1. Checks Python 3.8+
#   2. Copies files to install directory
#   3. Creates logs/ and reports/ directories
#   4. Copies config.ini.example → config.ini (if not already present)
#   5. Sets permissions
#   6. Prints crontab instructions
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/zabbix-html-reporter"
RUN_USER="zabbix"   # OS user that will run the reporter (can be any non-root user)

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --user)        RUN_USER="$2";    shift 2 ;;
        *)             echo "Unknown option: $1"; exit 1 ;;
    esac
done

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================="
echo " Zabbix HTML Reporter Install "
echo "=============================="
echo "Source      : $SRC_DIR"
echo "Install dir : $INSTALL_DIR"
echo "Run as user : $RUN_USER"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
PYTHON=$(command -v python3 || true)
if [[ -z "$PYTHON" ]]; then
    echo "[ERROR] python3 not found. Please install Python 3.8 or later."
    exit 1
fi

PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJ=$($PYTHON -c "import sys; print(sys.version_info.major)")
PYMIN=$($PYTHON -c "import sys; print(sys.version_info.minor)")

echo "[OK] Python $PYVER found at $PYTHON"

if (( PYMAJ < 3 || (PYMAJ == 3 && PYMIN < 8) )); then
    echo "[ERROR] Python 3.8 or later is required (found $PYVER)."
    exit 1
fi

# ── Create install directory ──────────────────────────────────────────────────
echo "[*] Creating directories …"
mkdir -p "$INSTALL_DIR"/{logs,reports}

# ── Copy source files ─────────────────────────────────────────────────────────
echo "[*] Copying files …"
cp -r "$SRC_DIR/zbx_report"           "$INSTALL_DIR/"
cp    "$SRC_DIR/zbx_reporter.py"      "$INSTALL_DIR/"
cp    "$SRC_DIR/requirements.txt"     "$INSTALL_DIR/"
cp    "$SRC_DIR/crontab.example"      "$INSTALL_DIR/"
cp    "$SRC_DIR/config.ini.example"   "$INSTALL_DIR/"

# Config: only copy example if config.ini does not exist
if [[ ! -f "$INSTALL_DIR/config.ini" ]]; then
    cp "$SRC_DIR/config.ini.example" "$INSTALL_DIR/config.ini"
    echo "[*] Created config.ini from example — EDIT IT before running!"
else
    echo "[*] config.ini already exists — skipping (not overwritten)."
fi

# ── Permissions ───────────────────────────────────────────────────────────────
echo "[*] Setting permissions …"

# Make main script executable
chmod +x "$INSTALL_DIR/zbx_reporter.py"

# Protect the config file (contains credentials)
chmod 640 "$INSTALL_DIR/config.ini"

# Set ownership if user exists
if id "$RUN_USER" &>/dev/null; then
    chown -R "$RUN_USER":"$RUN_USER" "$INSTALL_DIR"
    echo "[OK] Ownership set to $RUN_USER:$RUN_USER"
else
    echo "[WARN] User '$RUN_USER' not found — skipping chown."
    echo "       Manually run: chown -R <user>:<group> $INSTALL_DIR"
fi

# ── Create wrapper script ─────────────────────────────────────────────────────
WRAPPER="/usr/local/bin/zbx_reporter"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
exec $PYTHON $INSTALL_DIR/zbx_reporter.py "\$@"
EOF
chmod +x "$WRAPPER"
echo "[OK] Wrapper created: $WRAPPER"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo " Installation complete!"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit the configuration:"
echo "       $INSTALL_DIR/config.ini"
echo ""
echo "  2. Test a report:"
echo "       zbx_reporter --type hourly --format html --output-dir /tmp"
echo "     or:"
echo "       $PYTHON $INSTALL_DIR/zbx_reporter.py --type hourly --format html --output-dir /tmp"
echo ""
echo "  3. Add to crontab (see $INSTALL_DIR/crontab.example):"
echo "       crontab -u $RUN_USER -e"
echo ""
echo "  4. View generated reports:"
echo "       ls -lh $INSTALL_DIR/reports/"
echo ""
