# Kiosco de Consulta de Precios

*Kiosco táctil para consultar precios por código de barras, conectado en tiempo real a Odoo*

## Por qué lo hice

Este problema venía arrastrándose desde hace años cuando llegó a mis manos, y en vez de tratarlo como una tarea aislada de captura de datos, lo abordé como un problema de sistema completo, diseñando un protocolo de trabajo y automatizando parte del proceso con una herramienta propia. Este kiosco es la pieza que conecta ese trabajo de análisis, automatización e integración con el cliente final, la parte que la gente ve y usa todos los días. Cada vez que lo veo funcionando siento que valió la pena tomármelo en serio, sin que nadie me lo pidiera exactamente así.

## El problema

El negocio funciona bajo un modelo de autoservicio, el cliente recorre el punto de venta, toma los productos por su cuenta y paga al final en caja. Ese modelo nunca vino acompañado de una forma de que el cliente mismo consultara un precio, y con los años el catálogo terminó con productos sin código de barras o con códigos mal cargados en el sistema. Corregir eso producto por producto no es algo que una sola persona resuelva de un día para otro, así que hacía falta algo que funcionara ya, con el catálogo incompleto, en vez de esperar a que estuviera perfecto para empezar a dar valor.

## La solución

El kiosco deja que cualquier cliente pase el código de barras de un producto y vea de inmediato su nombre, precio e imagen, sin depender de que un empleado esté disponible en ese momento. Cuando el código no está en el sistema, en vez de fallar en silencio o mostrar un error, redirige al cliente a una caja con un mensaje pensado para que la experiencia no se sienta como una falla. Eso no completa el catálogo de un momento a otro, pero convierte cada intento fallido en una señal visible de qué producto sigue sin código, y esa presión termina donde debe terminar, en quien es responsable de mantener esos datos, no en el cliente que solo quería saber un precio.

Corre desde un navegador común, sin instalar módulos adicionales de Odoo ni depender de licencias extra, así que funciona bien incluso en equipos limitados y aprovecha lo que ya estaba instalado en el punto de venta. Construirlo por fuera también dio control total sobre lo que ve el cliente, desde el tamaño de la letra hasta el mensaje que aparece cuando un producto todavía no tiene código, algo que una app genérica no iba a dejar ajustar así.

## Cómo funciona

El servidor corre en Flask sobre Waitress en un equipo central de la tienda y se conecta a Odoo por XML-RPC, consultando el producto por su código de barras en el instante en que se escanea. Cada terminal es simplemente un computador con un lector de código de barras conectado y Microsoft Edge abierto en modo kiosko de pantalla completa, apuntando a ese servidor, así que varios puntos de la tienda comparten el mismo catálogo sin tener cada uno su propia copia de los datos.

El modo kiosko de Edge no se cierra con un simple Alt+F4, así que cada terminal corre también un agente pequeño en Python que escucha únicamente en su propia máquina y se activa tocando el logo cinco veces seguidas en la pantalla, cerrando Edge solo en ese equipo. De esa forma la salida del kiosko no depende del servidor central ni afecta a las demás terminales cuando alguien necesita volver a Windows.

## Herramientas usadas

- Python (Flask, Waitress)
- XML-RPC (Odoo ORM)
- HTML, CSS y JavaScript puro, sin frameworks de frontend
- Windows Service

## Uso

1. Copia `credenciales_ejemplo.py` como `credenciales.py` en la misma carpeta y completa tus datos reales de Odoo.
2. Ajusta la IP del servidor en `iniciar_kiosco.bat`.
3. En el servidor, corre `servidor_kiosco.py` (se recomienda instalarlo como servicio de Windows con NSSM para que arranque solo).
4. En cada terminal, usa `iniciar_kiosco_silencioso.vbs` para abrir el kiosco sin ventanas de consola visibles.

---

*Este repositorio contiene una versión genérica del código real. Se removieron la dirección IP del servidor, el nombre y el logo de la tienda, y cualquier dato que pudiera identificar la infraestructura donde opera el sistema.*
