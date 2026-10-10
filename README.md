# EH4000 Structural Integrity Dashboard

Dashboard local de integridad estructural para el equipo **EH4-01**, limitado a **Tijeras y spindle (suspensión delantera)** y los puntos **SD-01…SD-04**. La aplicación usa la historia QA ya validada; no edita ni reescribe el libro Excel de origen.

## Requisitos y arranque en Windows

Con Anaconda o Miniconda instalado, desde la raíz del proyecto:

```powershell
conda env create -f environment.yml
conda activate eh4000-integrity
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

En otra terminal:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Abrir `http://127.0.0.1:5173`. La documentación interactiva del API está en `http://127.0.0.1:8000/docs`. Para compilar el cliente: `cd frontend; npm run build`.

### Si la interfaz no inicia

El servidor de desarrollo debe mantener activa la preparación de dependencias de
Vite (`optimizeDeps`). React publica entradas CommonJS; desactivar esa preparación
produce errores como `react/jsx-runtime.js does not provide an export named 'jsx'`
y deja la pantalla en «Iniciando el dashboard». La configuración incluye
explícitamente React y sus runtimes JSX para convertirlos a módulos de navegador.
Después de actualizar la configuración, recargar la página. Si el servidor se
había detenido, ejecutar otra vez `npm run dev` desde `frontend`.

Para usar la versión compilada, desde `frontend`:

```powershell
npm run build
npm run preview -- --port 4173 --strictPort
```

Esa versión se abre en `http://127.0.0.1:4173`. Los cambios de código requieren una
nueva compilación; el backend debe continuar activo en el puerto 8000.

## Funciones

- Resumen del estado histórico y última inspección disponible (la pantalla no afirma que los datos sean telemetría en vivo).
- Visor 3D del STL de suspensión delantera, selección de punto, cámara y opacidad, indicadores de severidad y calibración manual de hotspots.
- Serie de inspección por fecha/horómetro, longitud RAW, límites oficiales, estado estructural, delta con tolerancia operacional de 10 mm, tasas RAW/efectivas y advertencia específica para cambios a través de N/I.
- Registro de nuevas inspecciones, con cuatro puntos requeridos y opción explícita N/I; el valor en blanco no se convierte a cero.
- Reglas determinísticas de mantenimiento, órdenes de trabajo con historial de estados, evidencia local, QA y calibración.

Las acciones de mantenimiento sugeridas no se convierten automáticamente en órdenes aprobadas ni programadas. El cambio de estado de una orden es explícito y auditado.

## Datos y límites de interpretación

- Libro fuente: `DATOSCRUDOS/EH4000_historial_grietas.xlsx`. La carga de la app utiliza `outputs/maintenance/maintenance_features.csv`, `outputs/maintenance/zone_snapshot.csv` y salidas QA vinculadas al hash SHA-256 del libro.
- El backend importa esas inspecciones históricas de forma idempotente a `backend/eh4000_integrity.sqlite3`. No se debe borrar esa base si se desea conservar registros nuevos, órdenes, evidencia o calibraciones creados localmente.
- `0 mm` es una medición disponible sin grieta detectable; N/I es una medición no disponible.
- `MEASUREMENT_TOLERANCE_MM = 10` se utiliza únicamente para interpretar cambios entre inspecciones. Los estados Normal/Alerta/Crítico usan la longitud RAW y los límites oficiales sin tolerancia.
- Un cambio entre la última medición válida anterior a N/I y la primera posterior se presenta como cambio a través de intervalo incompleto, con bandera. No es una observación consecutiva ni una tasa ordinaria.
- No se ejecuta forecasting, ML, imputación, smoothing ni interpolación.
- El STL suministrado se conserva como malla técnica de una sola pieza. Sus unidades fuente no están documentadas y la malla no es watertight. Los cuatro hotspots iniciales se mapearon provisionalmente desde el esquema SD al marco local del STL (tijera y spindle por lado); quedan sin confirmar hasta que un ingeniero revise y, si hace falta, ajuste su ubicación en el visor.
- El I3D del simulador depende de recursos externos/proprietary y no se presenta como geometría integrada. La aplicación muestra el STL real y el esquema SD del formato de inspección.
- Referencia visual: `frontend/public/assets/schemes/sd_inspection_reference.png`.

## Verificación local

```powershell
conda activate eh4000-integrity
python -m pytest backend/tests -q
cd frontend
npm run build
```

La base de pruebas usa una SQLite temporal aislada. La API conserva la base normal cuando corre el dashboard.

## Almacenamiento local

`backend/uploads/` contiene evidencias cargadas por usuarios; `backend/eh4000_integrity.sqlite3` contiene los datos operativos locales. Conviene respaldar ambos antes de mover o reinstalar el proyecto. Las variables `EH4000_DB_PATH` o `EH4000_DATABASE_URL` permiten seleccionar otra base de desarrollo.

## Publicación como sitio web

### Demostración académica sin servidor

La opción recomendada para evaluación es una publicación estática en GitHub Pages. El evaluador abre el enlace en su navegador y puede recorrer el dashboard, el camión GLB, el STL de suspensión, las 25 inspecciones validadas, gráficas, QA, alertas y recomendaciones. El sitio marca claramente que es una **demostración histórica de solo consulta**: no presenta como guardadas inspecciones, órdenes o evidencias nuevas. El archivo `scripts/export_static_demo.py` crea el paquete JSON desde una base temporal nueva, de modo que no publica registros privados creados localmente.

El workflow `.github/workflows/pages.yml` genera el paquete, compila React con rutas compatibles con GitHub Pages y publica `frontend/dist`. Para activar el enlace, habilitar **Settings → Pages → Source: GitHub Actions** en el repositorio y subir estos cambios a `main`. La dirección será `https://Luis3070.github.io/TEPARCIAL2/` cuando termine la publicación. No se necesita cuenta adicional ni servidor de Python para los visitantes.

La versión estática no reemplaza la instalación completa descrita abajo cuando se requiere registrar información compartida. El historial Excel y el Word fuente no se entregan directamente al navegador; se exportan únicamente las respuestas necesarias para la interfaz.

La versión de producción sirve la interfaz React compilada y la API FastAPI desde **una sola dirección**. El navegador del visitante no necesita Python, Node, Anaconda ni instalar nada. Las rutas internas, como `/structural-3d` y `/evidence`, también se abren directamente. La API utiliza `/api` en el mismo origen.

Se incluyen `Dockerfile`, `compose.yaml`, `compose.public.yaml` y `Caddyfile` para alojar la aplicación completa en una máquina Linux con almacenamiento persistente. En esa instalación, SQLite y las evidencias se guardan en `deployment-data/`, fuera de la imagen. El contenedor usa un único proceso/worker para SQLite.

### Preparación de la cuenta y el enlace

1. Crear una máquina Linux en un alojamiento gratuito que permita Docker y conserve el disco. Una opción es **Oracle Cloud Always Free**, eligiendo explícitamente una instancia y volumen marcados *Always Free*. Oracle suele pedir tarjeta para verificar la identidad y puede carecer de capacidad en una región. No cambiar a recursos de pago. También se puede usar cualquier servidor Linux propio disponible para la tarea.
2. Crear un subdominio gratuito, por ejemplo en DuckDNS, y dirigirlo a la IP pública de la máquina. Abrir TCP 80 y 443 en el firewall de la nube y del sistema.
3. Llevar este repositorio al servidor. Revisar antes los permisos de redistribución del archivo `frontend/public/assets/hitachi_eh4000_fs25.glb`: el mod de origen no documenta licencia en los archivos entregados. Aunque se use en una tarea, un enlace público permite descargar el GLB. Si no se cuenta con permiso, sustituirlo por un recurso autorizado antes de publicar.
4. Copiar `.env.example` a `.env` y asignar `EH4000_DOMAIN` al subdominio y `EH4000_SITE_PASSWORD` a una contraseña larga. El usuario de acceso es `eh4000`. Compartir la contraseña solo con quienes deban usar el tablero. El archivo `.env` está ignorado por Git.
5. En el servidor Linux, crear el almacenamiento con `sudo mkdir -p deployment-data/uploads` y `sudo chown -R 10001:10001 deployment-data`. Ejecutar `docker compose -f compose.yaml -f compose.public.yaml up -d --build`. Caddy obtiene y renueva HTTPS automáticamente cuando DNS y puertos ya funcionan. El enlace queda `https://<EH4000_DOMAIN>/`.

Para revisar registros: `docker compose -f compose.yaml -f compose.public.yaml logs --tail=100`. Antes de actualizar o mover el servidor, respaldar `deployment-data/` y los volúmenes `caddy_data` y `caddy_config`. La historia validada se importa al iniciar solo si no existe en la base. La base SQLite local de Windows y las evidencias locales **no se transfieren automáticamente** al servidor.

Sin cuenta de alojamiento y subdominio todavía no existe una URL pública real; `127.0.0.1` solo abre en el equipo que ejecuta la aplicación. Un servicio gratuito sin disco persistente perdería las nuevas inspecciones, órdenes y evidencias al reiniciarse, por eso no se recomienda para la entrega funcional.
