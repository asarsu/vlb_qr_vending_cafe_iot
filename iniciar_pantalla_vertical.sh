#!/bin/bash
export DISPLAY=:0

# Esperamos 2 segundos a que el servidor de video se estabilice
sleep 2

# Detectamos y giramos la pantalla
PANTALLA=$(xrandr | grep " connected" | cut -d' ' -f1 | head -n1)
xrandr --output "$PANTALLA" --rotate right

# Lanzamos el micro-gestor de ventanas en segundo plano (OBLIGATORIO EL & AL FINAL)
matchbox-window-manager -use_titlebar no &

# Lanzamos tu interfaz gráfica (Modular v2.0)
exec python3 /home/pi/python_localQR_v2.0/main.py