@echo off
REM =================================================================
REM  INICIAR KIOSCO DE PRECIOS - PROYECTO NAIROBI
REM  -----------------------------------------------------------
REM  Doble clic aqui (o en un acceso directo hacia este archivo)
REM  para abrir el kiosco. Para salir y volver a Windows normal:
REM  toca el logo 5 veces en la pantalla.
REM =================================================================

REM --- 1) Prende el "agente" en silencio, sin ninguna ventana ---
REM     Es el que va a estar escuchando para cerrar Edge cuando
REM     toques el logo 5 veces. pythonw.exe (con "w") es la version
REM     de Python que corre SIN mostrar ventana negra de consola.
REM     Ajusta la ruta si guardaste kiosco_agente_local.py en otro lugar.
start "" pythonw.exe "C:\Kiosco\agente_local_salida.py"

REM --- 2) Le da 2 segundos de margen al agente para que arranque ---
REM     antes de abrir el navegador (asi la señal de "salir" ya
REM     tiene quien la escuche desde el primer segundo).
timeout /t 2 >nul

REM --- 3) Abre Edge en modo kiosko, apuntando al servidor central ---
REM     Reemplaza 192.168.1.XXX por la IP real de tu servidor en la red local.
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk http://192.168.1.XXX:55555 --edge-kiosk-type=fullscreen --no-first-run

REM Cuando cierres Edge tocando el logo 5 veces, no queda nada
REM abierto de este .bat: se cierra por si solo.
