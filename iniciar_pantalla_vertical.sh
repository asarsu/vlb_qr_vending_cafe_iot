#!/bin/bash
export DISPLAY=:0

# Esperamos 2 segundos a que el servidor de video se estabilice
sleep 2

# Detectamos y giramos la pantalla
PANTALLA=$(xrandr | grep " connected" | cut -d' ' -f1 | head -n1)
xrandr --output "$PANTALLA" --rotate right

# Lanzamos el micro-gestor de ventanas en segundo plano (OBLIGATORIO EL & AL FINAL)
matchbox-window-manager -use_titlebar no &

# Lanzamos tu interfaz gráfica (Modular v2.1)
DIR_PROYECTO="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR_PROYECTO/main.py"