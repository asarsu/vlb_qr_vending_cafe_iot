"""
main.py
=======
Punto de entrada ultra-limpio para el Kiosco QR Vending v2.0.
Inicia la aplicación modularizada respetando Clean Architecture y SOLID.
"""

import os
import sys

# Asegurar que el directorio raíz del proyecto esté en el PYTHONPATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.app import create_app


def main():
    app = create_app()
    app.start()


if __name__ == "__main__":
    main()
