# vlb_qr_vending_iot — Kiosco QR Vending (Snakky)

Proyecto de implementación de pagos cashless (QR) para máquinas vending con protocolo MDB Waferstar y pagos QR Banco BISA / SIP (MC4). Arquitectura modular basada en principios **SOLID** y **Clean Architecture**.

---

## 📁 Estructura del Proyecto

```text
python_localQR_v2.0/
├── main.py                       # Punto de entrada principal y ultra-limpio
├── qr01_univalle_snakky_v1.4.py  # Wrapper de retrocompatibilidad
├── requirements.txt              # Dependencias pip
├── .env.example                  # Plantilla de variables de entorno
├── iniciar_pantalla_vertical.sh  # Script de inicio en Raspberry Pi (X11)
├── public/                       # Assets gráficos (logo, iconos)
├── logs/                         # Registros de ciclos de compra
├── tests/                        # Suite de pruebas automatizadas
│   ├── test_mdb_protocol.py
│   └── test_state_and_config.py
└── src/                          # Código fuente modular
    ├── config/
    │   └── settings.py           # AppConfig tipada con soporte de variables de entorno
    ├── core/
    │   ├── coordinator.py        # VendingCoordinator & TouchHitboxManager
    │   └── state.py              # VendingState (thread-safe)
    ├── hardware/
    │   ├── mdb_protocol.py       # MdbSecurityController (Candado de precios & cálculo MDB)
    │   └── serial_driver.py      # SerialMdbDriver (Comunicación serie RS232-MDB)
    ├── logging_utils/
    │   └── logger.py             # LogManager (Logs aislados por ciclo de venta)
    ├── payment/
    │   ├── bisa_client.py        # BisaApiClient (Generación QR y Polling)
    │   └── webhook_server.py     # WebhookServer (Receptor Flask en segundo plano)
    ├── ui/
    │   └── vending_ui.py         # VendingUI (Renderizado Canvas Tkinter)
    └── app.py                    # VendingApplication (Composición e Inyección de Dependencias)
```

---

## 🚀 Despliegue y Ejecución

### 1. Instalación de dependencias del sistema (Raspberry Pi OS / Debian / Ubuntu)
```bash
sudo apt update
sudo apt install -y python3-tk python3-pil python3-requests python3-serial matchbox-window-manager x11-xserver-utils
```

### 2. Instalación de dependencias Python
```bash
pip3 install -r requirements.txt
```

### 3. Ejecución directa
```bash
python3 main.py
```

O mediante el wrapper legacy:
```bash
python3 qr01_univalle_snakky_v1.4.py
```

### 4. Ejecución en Kiosco / Pantalla Vertical (Raspberry Pi)
El script [`iniciar_pantalla_vertical.sh`](file:///home/andres/Documentos/Proyecto-QR-2025/python_localQR_v2.0/iniciar_pantalla_vertical.sh) rota la pantalla e inicializa el gestor de ventanas liviano antes de ejecutar `main.py`:
```bash
bash iniciar_pantalla_vertical.sh
```

---

## 🧪 Pruebas Unitarias
Para ejecutar la suite de pruebas automatizadas:
```bash
python3 -m unittest discover -s tests
```
