#!/usr/bin/env bash
# ==============================================================================
# scripts/check_and_run.sh
# ==============================================================================
# Script de auto-arranque y watchdog de conectividad para Kiosco QR Vending.
# Verifica:
#   1. Conectividad general a Internet (DNS / Ping / HTTP)
#   2. Ruta y túnel al webhook de pagos (qr01.vendingbolivia.com)
#   3. Ruta y túnel al servicio de acceso remoto SSH (ssh-qr01.vendingbolivia.com)
#
# Una vez validadas las dependencias, lanza la aplicación o el gestor de pantalla.
# En caso de desconexión o fallo, el script termina con código de error para que
# systemd reinicie el ciclo automáticamente de acuerdo a la política Restart=always.
# ==============================================================================

set -u

# Configuración de variables (con valores por defecto sobreescribibles por entorno)
APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
QR_HOST="${QR_HOST:-qr01.vendingbolivia.com}"
SSH_HOST="${SSH_HOST:-ssh-qr01.vendingbolivia.com}"
SSH_PORT="${SSH_PORT:-22}"
RETRY_DELAY="${RETRY_DELAY:-5}"
MAX_RETRIES="${MAX_RETRIES:-30}" # 30 intentos x 5s = 2.5 min máx por intento antes de reportar a systemd
DISPLAY_VALUE="${DISPLAY:-:0}"
ENABLE_GUI_ROTATION="${ENABLE_GUI_ROTATION:-1}"

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [AUTO-START] [INFO] $1"
}

log_warn() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [AUTO-START] [WARN] $1" >&2
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [AUTO-START] [ERROR] $1" >&2
}

# --- 1. Verificación de Internet básico ---
verificar_internet() {
    log_info "Verificando acceso a Internet básico..."
    local intento=1
    while [ "$intento" -le "$MAX_RETRIES" ]; do
        # Prueba resolución de nombres y ping / curl básico
        if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1 || ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 || curl -s -m 3 http://connectivitycheck.gstatic.com/generate_204 >/dev/null 2>&1; then
            log_info "Conectividad a Internet confirmada."
            return 0
        fi
        log_warn "Esperando conexión a Internet (intento $intento/$MAX_RETRIES)..."
        sleep "$RETRY_DELAY"
        intento=$((intento + 1))
    done
    log_error "No se pudo establecer conexión a Internet tras $MAX_RETRIES intentos."
    return 1
}

# --- 2. Verificación de túnel/ruta Callback Visa (qr01.vendingbolivia.com) ---
verificar_tunel_qr() {
    log_info "Verificando ruta y túnel al webhook: $QR_HOST ..."
    local intento=1
    while [ "$intento" -le "$MAX_RETRIES" ]; do
        # 1. Comprobar si el proceso del túnel cloudflared está activo localmente
        local cloudflared_activo=0
        if pgrep -x "cloudflared" >/dev/null 2>&1; then
            cloudflared_activo=1
        fi

        # 2. Comprobar resolución DNS
        if ! getent ahosts "$QR_HOST" >/dev/null 2>&1; then
            log_warn "DNS aún no resuelve $QR_HOST (intento $intento/$MAX_RETRIES)"
            sleep "$RETRY_DELAY"
            intento=$((intento + 1))
            continue
        fi

        # 3. Consultar HTTP/HTTPS
        # Nota: El webhook corre dentro de la misma app en el puerto 5000.
        # Si la app aún no arrancó, Cloudflare devolverá 502 Bad Gateway (indicando que el túnel
        # perimetral está conectado pero esperando que la app abra el puerto local).
        # Un código 530 o fallo de conexión curl indica que el túnel Cloudflare está caído.
        local http_code
        http_code=$(curl -k -s -o /dev/null -w "%{http_code}" -m 5 "https://$QR_HOST/api/pagos/callback" || echo "000")
        
        # Validar si recibimos respuesta válida de Cloudflare
        if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 500 ]; then
            log_info "Túnel y ruta Webhook QR confirmados OK (HTTP $http_code)."
            return 0
        elif [ "$http_code" = "502" ]; then
            # Cloudflare responde 502 porque el servidor local de la app aún no abre el puerto 5000.
            # Verificamos si cloudflared está corriendo o si la cabecera server=cloudflare está presente.
            log_info "Túnel Cloudflare detectado activo en $QR_HOST (HTTP 502 esperado: app aún no abierta en puerto local). Procediendo..."
            return 0
        elif [ "$cloudflared_activo" -eq 1 ] && [ "$http_code" != "000" ] && [ "$http_code" != "530" ]; then
            log_info "Túnel Cloudflare corriendo y resolviendo $QR_HOST. Procediendo..."
            return 0
        else
            log_warn "Túnel no disponible en $QR_HOST (HTTP $http_code, intento $intento/$MAX_RETRIES)"
        fi

        sleep "$RETRY_DELAY"
        intento=$((intento + 1))
    done

    log_error "No se confirmó túnel funcional en $QR_HOST tras $MAX_RETRIES intentos."
    return 1
}

# --- 3. Verificación de túnel/ruta Acceso Remoto SSH (ssh-qr01.vendingbolivia.com) ---
verificar_tunel_ssh() {
    log_info "Verificando ruta y túnel SSH: $SSH_HOST:$SSH_PORT ..."
    local intento=1
    while [ "$intento" -le "$MAX_RETRIES" ]; do
        # 1. Comprobar resolución DNS
        if ! getent ahosts "$SSH_HOST" >/dev/null 2>&1; then
            log_warn "DNS aún no resuelve $SSH_HOST (intento $intento/$MAX_RETRIES)"
            sleep "$RETRY_DELAY"
            intento=$((intento + 1))
            continue
        fi

        # 2. Comprobar puerto abierto TCP (usando nc, bash socket o curl si es cloudflare access)
        local ssh_ok=0
        if command -v nc >/dev/null 2>&1; then
            if nc -zv -w 4 "$SSH_HOST" "$SSH_PORT" >/dev/null 2>&1; then
                ssh_ok=1
            fi
        elif (echo > /dev/tcp/"$SSH_HOST"/"$SSH_PORT") >/dev/null 2>&1; then
            ssh_ok=1
        fi

        # Si el túnel SSH pasa por Cloudflare HTTP2/WebSocket (Cloudflare Access / browser proxy),
        # también verificamos si responde HTTPS:
        if [ "$ssh_ok" -eq 0 ]; then
            local https_code
            https_code=$(curl -k -s -o /dev/null -w "%{http_code}" -m 4 "https://$SSH_HOST" || echo "000")
            if [ "$https_code" -ge 200 ] && [ "$https_code" -lt 500 ]; then
                ssh_ok=1
            fi
        fi

        if [ "$ssh_ok" -eq 1 ]; then
            log_info "Túnel y ruta de acceso remoto SSH confirmados OK ($SSH_HOST)."
            return 0
        fi

        log_warn "Puerto o ruta SSH inaccesible en $SSH_HOST:$SSH_PORT (intento $intento/$MAX_RETRIES)"
        sleep "$RETRY_DELAY"
        intento=$((intento + 1))
    done

    log_error "No se pudo confirmar ruta SSH en $SSH_HOST tras $MAX_RETRIES intentos."
    return 1
}

# --- 4. Lanzar Entorno Gráfico y Aplicación ---
lanzar_aplicacion() {
    log_info "Todas las conexiones de red y túneles están confirmadas."
    log_info "Iniciando entorno gráfico y aplicación principal en: $APP_DIR"

    export DISPLAY="$DISPLAY_VALUE"

    # Preparar rotación de pantalla si está habilitado y xrandr está presente
    if [ "$ENABLE_GUI_ROTATION" = "1" ] && command -v xrandr >/dev/null 2>&1; then
        sleep 2
        PANTALLA=$(xrandr | grep " connected" | cut -d' ' -f1 | head -n1 || true)
        if [ -n "$PANTALLA" ]; then
            log_info "Configurando rotación vertical para display '$PANTALLA'..."
            xrandr --output "$PANTALLA" --rotate right || log_warn "xrandr no pudo rotar display"
        fi
    fi

    # Gestor de ventanas ligero si existe
    if command -v matchbox-window-manager >/dev/null 2>&1; then
        if ! pgrep -x "matchbox-window-manager" >/dev/null 2>&1; then
            log_info "Lanzando matchbox-window-manager..."
            matchbox-window-manager -use_titlebar no &
        fi
    fi

    cd "$APP_DIR" || {
        log_error "No se pudo cambiar al directorio $APP_DIR"
        exit 1
    }

    log_info "Ejecutando main.py..."
    # Usamos exec para que systemd monitoree directamente el proceso python
    exec python3 "$APP_DIR/main.py"
}

# --- Flujo Principal ---
main() {
    log_info "=== Iniciando Kiosco QR Vending Watchdog & Auto-Start ==="
    
    if ! verificar_internet; then
        exit 1
    fi

    if ! verificar_tunel_qr; then
        exit 2
    fi

    if ! verificar_tunel_ssh; then
        exit 3
    fi

    lanzar_aplicacion
}

main "$@"
