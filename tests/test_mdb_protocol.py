"""
tests/test_mdb_protocol.py
==========================
Pruebas unitarias para el controlador de seguridad y protocolo MDB.
Valida el cálculo de crédito en centavos exactos y el parsing del candado 1300.
"""

import unittest
from src.hardware.mdb_protocol import MdbSecurityController


class TestMdbProtocol(unittest.TestCase):

    def test_calcular_trama_credito_5bs(self):
        # 5.00 Bs = 500 cts -> 0x01F4 -> byte1=0x01, byte2=0xF4, chk=(0x03+0x01+0xF4)&0xFF = 0xF8
        trama = MdbSecurityController.calcular_trama_credito(5.00)
        self.assertEqual(trama, "0301F4F8")

    def test_calcular_trama_credito_10bs(self):
        # 10.00 Bs = 1000 cts -> 0x03E8 -> byte1=0x03, byte2=0xE8, chk=(0x03+0x03+0xE8)&0xFF = 0xEE
        trama = MdbSecurityController.calcular_trama_credito(10.00)
        self.assertEqual(trama, "0303E8EE")

    def test_parsear_vend_request_ascii_valido(self):
        # Trama 1300 con precio 500 cts (01F4) y producto #12 (000C) + chk
        texto = "130001F4000C00"
        hex_crudo = ""
        codigo, precio, centavos = MdbSecurityController.parsear_vend_request(texto, hex_crudo)
        self.assertEqual(codigo, "12")
        self.assertEqual(precio, 5.0)
        self.assertEqual(centavos, 500)

    def test_parsear_vend_request_hex_valido(self):
        # ASCII '130001F4000C00' en hex
        ascii_trama = "130001F4000C00"
        hex_crudo = ascii_trama.encode("ascii").hex()
        codigo, precio, centavos = MdbSecurityController.parsear_vend_request("", hex_crudo)
        self.assertEqual(codigo, "12")
        self.assertEqual(precio, 5.0)
        self.assertEqual(centavos, 500)

    def test_parsear_vend_request_invalido(self):
        texto = "0707"
        hex_crudo = "0707"
        codigo, precio, centavos = MdbSecurityController.parsear_vend_request(texto, hex_crudo)
        self.assertIsNone(codigo)
        self.assertIsNone(precio)
        self.assertIsNone(centavos)


if __name__ == "__main__":
    unittest.main()
