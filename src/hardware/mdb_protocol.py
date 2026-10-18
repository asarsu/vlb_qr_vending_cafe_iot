"""
src/hardware/mdb_protocol.py
============================
Implementa las reglas de negocio del protocolo MDB y el candado de precios.
"""

import re
from typing import Optional, Tuple


class MdbSecurityController:
    """Implementa las reglas de negocio del protocolo MDB y el candado de precios."""

    @staticmethod
    def calcular_trama_credito(monto_bs: float) -> str:
        """STX(03) + HIGH_BYTE + LOW_BYTE + CHECKSUM en centavos exactos."""
        centavos = int(round(monto_bs * 100))
        byte1 = (centavos >> 8) & 0xFF
        byte2 = centavos & 0xFF
        checksum = (0x03 + byte1 + byte2) & 0xFF
        trama = f"03{byte1:02X}{byte2:02X}{checksum:02X}"
        print(f"[MDB] Cálculo Crédito: Bs {monto_bs:.2f} ({centavos} cts) -> Trama: {trama}")
        return trama

    @staticmethod
    def parsear_vend_request(texto: str, hex_crudo: str) -> Tuple[Optional[str], Optional[float], Optional[int]]:
        """
        Decodifica la trama 1300 (Vend Request).
        Formato Waferstar: '1300' + PRECIO_HEX(4) + CODIGO_HEX(4) + CHK(2)
        Retorna: (codigo_str, precio_bs, centavos_extraidos)
        """
        cadena = texto if "1300" in texto else ""
        if not cadena and hex_crudo:
            try:
                decodificado = bytes.fromhex(hex_crudo).decode("ascii", errors="ignore").upper()
                if "1300" in decodificado:
                    cadena = decodificado
            except Exception:
                pass
            if not cadena and "1300" in hex_crudo:
                cadena = hex_crudo

        if "1300" in cadena:
            pos = cadena.find("1300")
            resto = cadena[pos + 4 :]
            if len(resto) >= 8:
                try:
                    precio_hex_str = resto[0:4]
                    item_hex_str = resto[4:8]
                    centavos = int(precio_hex_str, 16)
                    item_num = int(item_hex_str, 16)
                    precio_bs = round(centavos / 100.0, 2)
                    codigo_str = str(item_num)
                    print(f"[MDB CANDADO] Trama 1300 -> Código: #{codigo_str}, Precio: Bs. {precio_bs:.2f} ({centavos} cts)")
                    return codigo_str, precio_bs, centavos
                except Exception as e:
                    print(f"[MDB ERROR] Error decodificando valores ASCII de 1300: {e}")

        # Fallback por expresiones regulares si la trama viene fragmentada
        hallazgos = re.findall(r"\d+", texto)
        for h in hallazgos:
            if h not in ("1300", "0505", "0606", "1302", "1304", "0707"):
                return h, None, None

        return None, None, None
