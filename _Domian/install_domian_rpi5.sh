#!/bin/bash
# ══════════════════════════════════════════════════════════════
# DOMIAN — Script de instalación en Raspberry Pi 5
# Ejecutar como: bash install_domian_rpi5.sh
# ══════════════════════════════════════════════════════════════

set -e  # Detener en caso de error

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✅]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠️ ]${NC} $1"; }
err()  { echo -e "${RED}[❌]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[ℹ️ ]${NC} $1"; }

echo ""
echo "🏠 DOMIAN — Instalación en Raspberry Pi 5"
echo "══════════════════════════════════════════"
echo ""

# ── Verificar que es RPi 5 ─────────────────────────────────────
if ! grep -q "Raspberry Pi 5" /proc/cpuinfo 2>/dev/null; then
    warn "No se detectó RPi 5 en /proc/cpuinfo — continuando de todas formas"
fi

# ── Verificar arquitectura 64-bit ─────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    err "Se requiere OS 64-bit (aarch64). Detectado: $ARCH"
fi
log "Arquitectura: $ARCH ✅"

# ── Variables configurables ───────────────────────────────────
REPO_URL="https://github.com/elcesar/RuView.git"
BRANCH="domian-demo3"
INSTALL_DIR="$HOME/Documents/RuView"
SERVER_IP=$(hostname -I | awk '{print $1}')
HTTP_PORT=8000
UDP_PORT=5005

echo ""
info "Configuración:"
info "  Repo:      $REPO_URL"
info "  Branch:    $BRANCH"
info "  IP local:  $SERVER_IP"
info "  HTTP port: $HTTP_PORT"
info "  UDP port:  $UDP_PORT"
echo ""

# ══════════════════════════════════════════════════════════════
# PASO 1 — Actualizar sistema
# ══════════════════════════════════════════════════════════════
echo "──────────────────────────────────────────"
info "Paso 1/8 — Actualizando sistema..."
echo "──────────────────────────────────────────"
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    git curl wget build-essential pkg-config \
    libssl-dev python3 python3-pip python3-venv \
    sqlite3 libsqlite3-dev \
    mosquitto mosquitto-clients \
    ufw
log "Sistema actualizado ✅"

# ══════════════════════════════════════════════════════════════
# PASO 2 — Instalar Rust
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 2/8 — Instalando Rust..."
echo "──────────────────────────────────────────"
if command -v cargo &> /dev/null; then
    log "Rust ya instalado: $(rustc --version)"
else
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    log "Rust instalado: $(rustc --version)"
fi

# ══════════════════════════════════════════════════════════════
# PASO 3 — Clonar repositorio DOMIAN
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 3/8 — Clonando repositorio DOMIAN..."
echo "──────────────────────────────────────────"
if [ -d "$INSTALL_DIR" ]; then
    warn "Directorio ya existe — haciendo pull"
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout $BRANCH
    git pull origin $BRANCH
else
    mkdir -p "$HOME/Documents"
    git clone -b $BRANCH "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
log "Repositorio listo en $INSTALL_DIR ✅"

# ══════════════════════════════════════════════════════════════
# PASO 4 — Compilar servidor RuView
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 4/8 — Compilando servidor RuView..."
info "⏳ Puede tardar 10-15 minutos en RPi 5..."
echo "──────────────────────────────────────────"
cd "$INSTALL_DIR/v2"
source "$HOME/.cargo/env"
cargo build --release -p wifi-densepose-sensing-server
log "Servidor compilado ✅"

# ══════════════════════════════════════════════════════════════
# PASO 5 — Entorno Python
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 5/8 — Configurando entorno Python..."
echo "──────────────────────────────────────────"
python3 -m venv "$HOME/domian_env"
source "$HOME/domian_env/bin/activate"
pip install --quiet websockets requests numpy scikit-learn opencv-python
log "Entorno Python listo ✅"

# ══════════════════════════════════════════════════════════════
# PASO 6 — Crear directorios de datos
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 6/8 — Creando estructura de datos..."
echo "──────────────────────────────────────────"
mkdir -p "$INSTALL_DIR/_Domian/demo/data"
mkdir -p "$INSTALL_DIR/_Domian/demo/models"
mkdir -p "$INSTALL_DIR/v2/data/recordings"
mkdir -p "$INSTALL_DIR/models/pretrained"
log "Directorios creados ✅"

# ══════════════════════════════════════════════════════════════
# PASO 7 — Configurar firewall
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 7/8 — Configurando firewall..."
echo "──────────────────────────────────────────"
sudo ufw allow 22/tcp    comment "SSH"
sudo ufw allow 8000/tcp  comment "RuView HTTP"
sudo ufw allow 8765/tcp  comment "RuView WebSocket"
sudo ufw allow 5005/udp  comment "RuView UDP ESP32"
sudo ufw allow 8123/tcp  comment "Home Assistant"
sudo ufw --force enable
log "Firewall configurado ✅"

# ══════════════════════════════════════════════════════════════
# PASO 8 — Crear servicio systemd
# ══════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────"
info "Paso 8/8 — Configurando servicio systemd..."
echo "──────────────────────────────────────────"

cat > /tmp/domian.service << EOF
[Unit]
Description=DOMIAN RuView Sensing Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR/v2
ExecStartPre=/bin/sleep 5
ExecStart=$INSTALL_DIR/v2/target/release/sensing-server \\
  --source esp32 \\
  --bind-addr 0.0.0.0 \\
  --udp-port $UDP_PORT \\
  --http-port $HTTP_PORT \\
  --allowed-host $SERVER_IP \\
  --allowed-host localhost \\
  --node-positions "0,0,1.5;0,3.5,1.5;5.7,3.5,1.5;5.7,0,1.5" \\
  --load-rvf $INSTALL_DIR/_Domian/demo/models/laoracion.rvf
ExecStartPost=/bin/sleep 8
ExecStartPost=/usr/bin/curl -s -X POST http://localhost:$HTTP_PORT/api/v1/config/dedup-factor -H "Content-Type: application/json" -d '{"factor": 4.0}'
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/domian.service /etc/systemd/system/domian.service
sudo systemctl daemon-reload
sudo systemctl enable domian.service
log "Servicio systemd configurado ✅"

# ══════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════
echo ""
echo "══════════════════════════════════════════"
echo "🟢 DOMIAN instalado correctamente en RPi 5"
echo "══════════════════════════════════════════"
echo ""
info "IP del servidor: $SERVER_IP"
echo ""
echo "Próximos pasos manuales:"
echo ""
echo "1. Copia el modelo calibrado desde la Mac:"
echo "   scp usuario@192.168.0.8:~/Documents/RuView/_Domian/demo/models/laoracion.rvf \\"
echo "       $INSTALL_DIR/_Domian/demo/models/"
echo ""
echo "2. Copia el modelo adaptativo:"
echo "   scp usuario@192.168.0.8:~/Documents/RuView/v2/data/adaptive_model.json \\"
echo "       $INSTALL_DIR/v2/data/"
echo ""
echo "3. Reprovisiona los nodos ESP32-S3 con la nueva IP:"
echo "   python3 provision.py --target-ip $SERVER_IP --node-id 1 ..."
echo ""
echo "4. Inicia el servidor:"
echo "   sudo systemctl start domian"
echo "   sudo systemctl status domian"
echo ""
echo "5. Verifica:"
echo "   curl http://$SERVER_IP:$HTTP_PORT/api/v1/nodes"
echo ""
echo "Dashboard: http://$SERVER_IP:$HTTP_PORT/ui/index.html"
echo ""
