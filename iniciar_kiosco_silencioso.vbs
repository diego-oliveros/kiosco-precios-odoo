' =================================================================
' LANZADOR SILENCIOSO DEL KIOSCO - PROYECTO NAIROBI
' -----------------------------------------------------------------
' Este archivo NO abre nada por si mismo: solo le pide a Windows
' que corra iniciar_kiosco.bat de forma invisible (el "0" de abajo
' significa "ventana oculta"), para que ni siquiera se alcance a
' ver el parpadeo de la ventanita negra de la consola.
'
' Uso: en vez de hacer doble clic en iniciar_kiosco.bat, haz doble
' clic aqui. El resultado es el mismo (agente + Edge en kiosko),
' solo que sin ningun parpadeo visible.
'
' Ajusta la ruta de abajo si guardaste el .bat en otro lugar.
' =================================================================
Set objShell = CreateObject("WScript.Shell")
objShell.Run """C:\Kiosco\iniciar_kiosco.bat""", 0, False
