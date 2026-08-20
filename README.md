# Kiosco de Consulta de Precios

Kiosco táctil para consultar precios por código de barras conectado en tiempo real a Odoo y diseñado para hardware reutilizado.

## Por qué lo hice

Este problema venía arrastrándose desde hace años cuando llegó a mis manos y en vez de tratarlo como una tarea aislada de captura de datos lo abordé como un problema de sistema completo diseñando un protocolo de trabajo y automatizando parte del proceso con una herramienta propia. Este kiosco es la pieza que conecta ese trabajo de análisis y automatización con el cliente final siendo la parte que la gente ve y usa todos los días. Cada vez que lo veo funcionando siento que valió la pena tomármelo en serio sin que nadie me lo pidiera exactamente así. 

El nombre Proyecto Nairobi presente en el código de este kiosco y en mi otro repositorio del Kardex es una dedicatoria a mi hija. Llevan el mismo nombre porque este script aprovecha los datos de esa anterior integración agrupando ambos trabajos bajo la misma iniciativa personal.

## El problema

El negocio funciona bajo un modelo de autoservicio donde el cliente recorre el punto de venta toma los productos por su cuenta y paga al final en caja. Ese modelo nunca vino acompañado de una forma de que el cliente mismo consultara un precio y con los años el catálogo terminó con productos sin código de barras o con códigos mal cargados en el sistema. Corregir eso producto por producto no es algo que una sola persona resuelva de un día para otro así que hacía falta algo que funcionara ya con el catálogo incompleto en vez de esperar a que estuviera perfecto para empezar a dar valor.

## La solución

Para materializar una solución inmediata sin depender de presupuestos extra rescaté un computador que el negocio tenía en desuso y lo convertí en un punto de consulta táctil. 

El kiosco deja que cualquier cliente pase el código de barras de un producto y vea de inmediato su nombre el precio y la imagen sin depender de que un empleado esté disponible. Cuando el producto todavía no tiene código cargado el sistema redirige al cliente a una caja puntual con un mensaje pensado para sonar a ayuda evitando que la experiencia del cliente dependa de que el inventario esté perfecto. 

El programa corre desde un navegador común sin instalar módulos extra de Odoo ni depender de licencias adicionales, funcionando de forma estable incluso en hardware reciclado de bajas prestaciones. Construirlo por fuera dio control total sobre la interfaz desde el tamaño de la letra hasta la gestión de errores logrando resultados que una aplicación genérica nunca permite.

## Cómo funciona

El servidor corre en Flask sobre Waitress en un equipo central de la tienda y se conecta a Odoo por XML-RPC consultando el producto por su código de barras en el instante en que se escanea. 

Cada terminal es simplemente un computador reutilizado con un lector de código de barras conectado y Microsoft Edge abierto en modo kiosko de pantalla completa apuntando a ese servidor. Sumar una terminal nueva en cualquier punto de la tienda es tan simple como apuntar otro equipo a esa misma dirección sin instalar nada adicional en Odoo ni duplicar la configuración.

Como el modo kiosko de Edge no se cierra con un simple comando de teclado cada terminal corre también un agente pequeño en Python que escucha únicamente en su propia máquina. Este programa se activa tocando el logo cinco veces seguidas en la pantalla cerrando el navegador solo en ese equipo para que la salida del kiosko no dependa del servidor central ni afecte a las demás terminales cuando alguien necesita volver al entorno de Windows para mantenimiento.

El servidor reutiliza una sola sesión autenticada contra Odoo en vez de abrir una nueva en cada consulta, protegida con un candado para que varias terminales escaneando al mismo tiempo no interfieran entre sí, y cada llamada tiene un límite de tiempo para que una respuesta lenta de Odoo no deje sin servicio al resto de terminales. Cada código escaneado queda registrado con su resultado, lo que en el futuro permitirá priorizar qué productos completar primero en el catálogo en vez de depender de que alguien lo note por casualidad.

## Herramientas usadas

* Python Flask Waitress
* XML-RPC Odoo ORM
* HTML CSS y JavaScript puro
* Windows Service

## Uso

1. Copia credenciales_ejemplo.py como credenciales.py en la misma carpeta y completa tus datos reales de Odoo
2. Ajusta la IP del servidor en iniciar_kiosco.bat
3. En el servidor corre servidor_kiosco.py o instálalo como servicio de Windows con NSSM para que arranque solo
4. En cada terminal usa iniciar_kiosco_silencioso.vbs para abrir el kiosco sin ventanas de consola visibles
5. Coloca el logo, imagen de espera y favicon dentro de una carpeta `static/img/` junto al servidor, con los nombres `logo.png`, `espera.png` y `favicon.ico`. No se incluyen en este repositorio por pertenecer a la identidad visual de cada negocio.

--

*Este repositorio contiene una versión genérica del código real. Se removieron la dirección IP del servidor el nombre y el logo de la tienda junto con cualquier dato que pudiera identificar la infraestructura operativa.*
