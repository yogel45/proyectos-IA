# Guía de uso paso a paso

## Demostración en 5 minutos

1. **Arranca la app**

   ```bash
   pip install -r requirements.txt
   python run.py
   ```

2. **Define los puntos críticos** — pestaña *Puntos críticos*
   * Pulsa **Fondo desde cámara** (o sube una foto del espacio).
   * Haz clic sobre la imagen para trazar el polígono de la zona.
   * Ponle nombre, tipo, aforo y umbral de permanencia → **Guardar zona**.
   * Vienen cuatro zonas de ejemplo; se pueden editar o borrar.

3. **Analiza en vivo** — pestaña *Cámara en vivo*
   * **Iniciar cámara** y acepta el permiso del navegador.
   * Verás cajas con ID y tiempo de permanencia, zonas con su ocupación y los eventos
     apareciendo en tiempo real.
   * Ajusta *FPS de análisis* y *Resolución de envío* según la potencia de tu equipo.

4. **Analiza una grabación** — pestaña *Videos*
   * Arrastra uno o varios videos. Se procesan en segundo plano con barra de progreso.
   * Al terminar, haz clic en el trabajo: métricas, actividad por zona, línea de tiempo,
     eventos, personas seguidas y el video anotado para descargar.
   * ¿No tienes un video a mano? `python scripts/video_demo.py` genera uno sintético
     (para ese video usa el detector `motion` desde `config.json`, porque no hay personas reales).

5. **Revisa el panorama** — pestañas *Dashboard*, *Operación* y *Reportes*
   * *Dashboard*: ocupación en el tiempo, actividad por hora, zonas y alertas.
   * *Operación*: la cámara cruzada con el biométrico y las llamadas.
   * *Reportes*: filtra eventos, mira la evidencia y exporta a CSV.

## Conectar una cámara IP o RTSP

En *Cámara en vivo* → sección **Cámara del servidor / IP**, escribe la fuente y pulsa
*Conectar*:

* `0`, `1`, … → cámara conectada al equipo que corre el servidor
* `rtsp://usuario:clave@192.168.1.50:554/stream1` → cámara IP
* `http://192.168.1.60/video.mjpg` → cámara MJPEG

## Importar tus propios datos operativos

*Operación* → **Importar Excel**:

* Archivos con `Biometric` en el nombre se leen como nómina + marcajes
  (hoja `Nomina` y una hoja por mes).
* Archivos con `RingCentral` o `Call` se leen como historial de llamadas
  (una hoja por semana, columnas `Type, Direction, From, To, Extension, …`).

## Ajustar sensibilidad

| Síntoma | Ajuste |
|---|---|
| Detecta de más | Sube `conf_threshold` (0.45–0.55) |
| No detecta personas lejanas | Baja `conf_threshold` (0.25) o sube `imgsz` a 960 |
| Va lento | Baja `live_target_fps` / `video_target_fps`, o resolución de envío a 480 |
| Quiero más precisión | `"model": "yolo11s.pt"` y, si hay GPU, `"device": "0"` |
| Demasiadas alertas de permanencia | Sube el umbral de la zona en *Puntos críticos* |
| Divide a una persona en varios IDs | Sube `track_max_age` (40–60) o baja `track_iou_match` (0.25) |

Todo esto se cambia en `config.json` o con `POST /api/config`, sin reiniciar.

## Endpoints útiles

| Endpoint | Para qué |
|---|---|
| `GET /docs` | Documentación interactiva (OpenAPI) |
| `GET /api/metrics/summary?hours=24` | KPIs, series y alertas del dashboard |
| `GET /api/metrics/live` | Estado instantáneo de las sesiones activas |
| `GET /api/events?severity=critical&since_hours=24` | Bitácora filtrada |
| `GET /api/business/cross?day=2025-09-13` | Tabla horaria integrada |
| `GET /api/export/events.csv` | Exportación para Excel o BI |
| `WS  /ws/live` | Análisis cuadro a cuadro desde otra aplicación |

## Problemas frecuentes

| Problema | Causa y solución |
|---|---|
| El navegador no pide permiso de cámara | Requiere `localhost` o HTTPS. Si sirves en red, usa un proxy con TLS |
| `No se pudo abrir el video` | Formato sin códec en OpenCV: reconvierte con `ffmpeg -i entrada.avi salida.mp4` |
| El video anotado no se reproduce en la página | Sin `ffmpeg` se guarda en mp4v; usa el botón de descarga o instala ffmpeg |
| Detector en modo `motion` sin querer | Falta `ultralytics`: `pip install ultralytics` y reinicia; revisa con `python run.py --check` |
| Primer arranque lento | Descarga única del modelo YOLO (5 MB) a `models/` |
