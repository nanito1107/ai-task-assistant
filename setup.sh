#!/bin/bash
# ============================================================
#  AI Task Assistant - Script de Instalación para QNAP
#  Ejecutar UNA SOLA VEZ en el host QNAP via SSH
# ============================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

PROJECT_DIR="/share/Container/ai-task-assistant"

info "=== AI Task Assistant - Setup QNAP ==="
echo ""

# 1. Crear directorio del proyecto
info "Creando directorio del proyecto en: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 2. Verificar que docker-compose esté disponible
if ! command -v docker &>/dev/null; then
    error "Docker no está instalado. Instálalo desde Container Station."
fi

if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
    warn "docker-compose no encontrado. Usando 'docker compose' (plugin)."
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi
info "Usando: $COMPOSE_CMD"

# 3. Crear archivo .env si no existe
if [ ! -f ".env" ]; then
    info "Creando archivo .env desde plantilla..."
    cp .env.example .env
    warn "⚠  EDITA el archivo .env con tus datos antes de continuar"
    warn "   Archivo: $PROJECT_DIR/.env"
    echo ""
    echo "   Variables OBLIGATORIAS a completar:"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - TELEGRAM_CHAT_ID"
    echo "   - POSTGRES_PASSWORD"
    echo "   - APP_SECRET_KEY"
    echo ""
    read -p "¿Ya editaste el .env? (s/N): " resp
    [[ "$resp" =~ ^[sS]$ ]] || { warn "Edita el .env y ejecuta este script nuevamente."; exit 0; }
fi

# 4. Levantar servicios en orden
info "Iniciando servicios Docker..."
$COMPOSE_CMD up -d postgres redis
info "Esperando que PostgreSQL esté listo..."
sleep 10

$COMPOSE_CMD up -d ollama
info "Ollama iniciado. Descargando modelo (puede tardar varios minutos)..."
$COMPOSE_CMD up -d whisper
$COMPOSE_CMD up -d grafana
$COMPOSE_CMD up -d backend nginx

info "Esperando que todos los servicios estén saludables..."
sleep 15

# 5. Descargar el modelo de Ollama
MODEL=$(grep OLLAMA_MODEL .env | cut -d= -f2 || echo "llama3.2")
info "Descargando modelo Ollama: $MODEL"
$COMPOSE_CMD exec -T ollama ollama pull "$MODEL" || warn "Descarga del modelo en background, verificar con: docker logs ai_ollama"

# 6. Verificar estado
echo ""
info "=== Estado de los servicios ==="
$COMPOSE_CMD ps

echo ""
info "=== URLs de acceso ==="
ZEROTIER_IP=$(ip addr show | grep -oP '172\.\d+\.\d+\.\d+' | head -1 || echo "CONFIGURA_IP_ZEROTIER")
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "  🏠 Red local:"
echo "     Dashboard Grafana: http://$LOCAL_IP/grafana/"
echo "     API Backend:       http://$LOCAL_IP/api/"
echo "     Documentación API: http://$LOCAL_IP:8000/docs"
echo ""
echo "  🌐 Via ZeroTier (remoto):"
echo "     Dashboard Grafana: http://$ZEROTIER_IP/grafana/"
echo "     API Backend:       http://$ZEROTIER_IP/api/"
echo ""
info "=== Instalación completada ==="
