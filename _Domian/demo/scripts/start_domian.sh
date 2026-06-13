#!/bin/bash
# DOMIAN — Script de inicio completo

echo "🏠 Iniciando DOMIAN..."

# 1. Arrancar servidor
cd ~/Documents/RuView/v2
cargo run -p wifi-densepose-sensing-server -- \
  --source esp32 \
  --bind-addr 0.0.0.0 \
  --udp-port 5005 \
  --http-port 8000 \
  --allowed-host 192.168.0.8 \
  --allowed-host localhost \
  --node-positions "0,0,1.5;0,3.5,1.5;5.7,3.5,1.5;5.7,0,1.5" \
  --load-rvf ~/Documents/RuView/_Domian/demo/models/laoracion.rvf &

SERVER_PID=$!
echo "✅ Servidor iniciado (PID: $SERVER_PID)"

# 2. Esperar que arranque
sleep 8

# 3. Configurar dedup_factor
curl -s -X POST http://192.168.0.8:8000/api/v1/config/dedup-factor \
  -H "Content-Type: application/json" \
  -d '{"factor": 4.0}'
echo "✅ dedup_factor=4.0 configurado"

# 4. Arrancar logger en background
source ~/domian_env/bin/activate
python3 ~/Documents/RuView/_Domian/demo/scripts/ws_logger.py &
LOGGER_PID=$!
echo "✅ Logger iniciado (PID: $LOGGER_PID)"

# 5. Arrancar webhook HA en background
python3 ~/Documents/RuView/_Domian/demo/scripts/ruview_webhook.py &
WEBHOOK_PID=$!
echo "✅ Webhook HA iniciado (PID: $WEBHOOK_PID)"

echo ""
echo "🟢 DOMIAN activo"
echo "   Dashboard: http://192.168.0.8:8000/ui/index.html"
echo "   Observatory: http://192.168.0.8:8000"
echo ""
echo "Para detener: kill $SERVER_PID $LOGGER_PID $WEBHOOK_PID"

wait $SERVER_PID