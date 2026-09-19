# Demostración funcional — OfficeVision AI (Reto 4)

Capturas y resultados de una ejecución real del proyecto de video, con los números que
produjo el sistema. Todo lo que aparece aquí se puede reproducir.

**Cómo se reprodujo**

```bash
pip install -r requirements.txt
python run.py                         # http://127.0.0.1:8000
#   se subio una grabacion de pasillo con personas en movimiento
```

---

## 1. Detección, seguimiento y zonas sobre el video

Cuadro del **video anotado** que genera la aplicación (se descarga desde la
pestaña *Videos*):

![Video anotado con detección, seguimiento y zonas](img/video-anotado.jpg)

Lo que se ve en la imagen, todo generado por el sistema:

* **5 personas detectadas** simultáneamente, cada una con su identificador
  anónimo (`P2-0002`, `P2-0003`, `P2-0006`, `P2-0008`) y **el tiempo que lleva
  en escena** (24 s, 10 s, 8 s…).
* **La zona en la que está cada una** escrita junto a su caja (`Área de trabajo`,
  `Recepción`).
* **Las zonas dibujadas** con su nombre y su ocupación actual.
* **Rostros difuminados** automáticamente: la evidencia sirve para auditar sin
  identificar a nadie.
* Barra superior con el recuento en vivo y el modelo activo.

## 2. Dashboard

![Dashboard de OfficeVision AI](img/video-dashboard.png)

Resultados de la sesión mostrada (grabación de 720×404 a 59,9 fps, analizada 1 de
cada 10 cuadros → **393 cuadros analizados**):

| Métrica | Valor |
|---|---|
| Personas únicas seguidas | 12 |
| Pico simultáneo | 5 |
| Permanencia media por persona | 19,8 s |
| Ocupación promedio | 2,93 personas |
| Eventos registrados | 87 (2 sesiones) |
| Alertas críticas | 5 |
| Objetos reconocidos | 5 tazones |

Entradas y salidas por zona en esa sesión: Recepción 9/5 (pico 3), Área de trabajo
8/4 (pico 3), Sala de juntas 2/2, Pasillo 3/2.

## 3. Reportes y evidencia visual

![Reportes con eventos, personas seguidas y evidencia](img/video-reportes.png)

La bitácora completa, filtrable y exportable. Se ve el ciclo entero de una zona:
`zone_enter` → `zone_exit` con el tiempo dentro → `aforo_excedido` cuando se
supera el máximo. Abajo, las **capturas automáticas de los eventos críticos**,
con los rostros difuminados.

Desglose de los 87 eventos: 44 entradas a zona, 26 salidas, 8 objetos nuevos,
5 aforos excedidos, 2 objetos retirados y 2 resúmenes minuto a minuto.

## 4. Resultado de un video procesado

![Resultado del análisis de un video](img/video-resultado.png)

Por cada video subido: métricas, ocupación a lo largo del video, actividad por
zona, inventario de objetos reconocidos, la lista de personas seguidas con su
permanencia y el video anotado para descargar.

## 5. Detección automática de puntos críticos

![Zonas propuestas automáticamente](img/video-zonas-automaticas.png)

Las zonas **no vienen impuestas**. El botón *Detectar por actividad* las propone a
partir de las trayectorias ya registradas, separando permanencia de tránsito, y
cada propuesta llega con su justificación ("corredor de paso: 3.0 celdas por
muestra, densidad 0.1"). Se dibujan punteadas y sólo se guardan si se aceptan.
La otra vía, *Detectar desde la escena*, reconoce mobiliario y equipos en una foto
o video del lugar y agrupa lo que está junto.

## 6. Cámara en vivo

![Cámara en vivo](img/video-camara-vivo.png)

La cámara del navegador analizada cuadro a cuadro: cajas con identificador y
permanencia, ocupación por zona en tiempo real, inventario de objetos, descripción
de la escena en español y el flujo de eventos según ocurren.

## 7. Cruce con la operación de la oficina

![Operación: cámara, biométrico y llamadas](img/video-operacion.png)

La cámara puesta junto al biométrico de asistencia (25 empleados, 7 647 marcajes)
y al histórico de llamadas de RingCentral (4 000 llamadas), hora por hora, con
hallazgos automáticos del tipo *"10:00: 13 de 22 llamadas sin atender (59 %)"*.

---

