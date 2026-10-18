"""
qr01_univalle_snakky_v1.4.py
============================
Wrapper de retrocompatibilidad hacia la arquitectura modular v2.0.
Permite ejecutar el kiosco con la misma llamada tradicional:
    python3 qr01_univalle_snakky_v1.4.py
mientras utiliza la arquitectura limpia y modular de `src/`.
"""

from main import main

if __name__ == "__main__":
    main()
