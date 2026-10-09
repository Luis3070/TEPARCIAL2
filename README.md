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
- El STL suministrado se conserva como malla técnica de una sola pieza. Sus unidades fuente no están documentadas y la malla no es watertight. Los cuatro hotspots requieren calibración humana: sus coordenadas no se inventan ni se consideran verificadas hasta confirmarlas.
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
