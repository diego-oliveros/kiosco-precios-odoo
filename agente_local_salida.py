# =============================================================================
# AGENTE LOCAL DE SALIDA DE KIOSKO - PROYECTO NAIROBI
# =============================================================================
# Corre en cada terminal que muestra el kiosco (el equipo con Edge abierto en
# --kiosk apuntando al servidor central). Escucha solo en 127.0.0.1 y, cuando
# la página se lo pide (al 5to toque del logo), cierra Edge en ese mismo
# equipo. No depende del servidor central ni tiene credenciales de Odoo, así
# que el botón de salida sigue funcionando aunque el servidor esté caído.
# =============================================================================

import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

# Debe coincidir con CONFIG.PUERTO_AGENTE_LOCAL en servidor_kiosco.py
PUERTO_AGENTE = 55556


class ManejadorSalida(BaseHTTPRequestHandler):

    def _cors(self):
        # Permite que la página del kiosco (servida desde la IP del servidor
        # central, otro origen) pueda llamar a este agente local sin que el
        # navegador bloquee la petición.
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == '/salir-kiosko':
            try:
                subprocess.Popen(
                    ['taskkill', '/F', '/IM', 'msedge.exe', '/T'],
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                self.send_response(200)
            except Exception:
                self.send_response(500)
        else:
            self.send_response(404)
        self._cors()
        self.end_headers()

    def log_message(self, formato, *args):
        pass  # silencioso: no llenar la consola con cada toque de logo


if __name__ == '__main__':
    # Enlazado SOLO a 127.0.0.1: invisible e inalcanzable desde cualquier
    # otro equipo de la red, aunque conozcan la IP de este terminal.
    servidor = HTTPServer(('127.0.0.1', PUERTO_AGENTE), ManejadorSalida)
    print(f"Agente local de kiosko activo en http://127.0.0.1:{PUERTO_AGENTE} (solo este equipo)")
    servidor.serve_forever()
