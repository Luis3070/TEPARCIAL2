# EH4000 Structural Integrity Dashboard

Dashboard académico del equipo **EH4-01 (Hitachi EH4000)**. El análisis se limita a la suspensión delantera: **tijeras y spindles, puntos SD-01 a SD-04**. Parte de 25 inspecciones históricas validadas (100 lecturas) y conserva el Excel original sin modificarlo.

## Abrir la versión web

**Enlace para el evaluador:** [https://luis3070.github.io/TEPARCIAL2/](https://luis3070.github.io/TEPARCIAL2/)

Solo se necesita un navegador actual y conexión a Internet. No hay que instalar Python, Node, Anaconda ni iniciar un servidor. La página es una demostración con datos históricos, **no** telemetría en vivo.

Al entrar, la pantalla **Overview** resume la inspección seleccionada. En la barra lateral, **ACTIVE ASSET → EH4-01** abre la vista 3D del camión; **Select EH4-01 · Open Overview** vuelve al resumen. El camión es contexto visual. **Structural 3D** muestra el STL técnico de suspensión y los cuatro puntos SD; la posición de los marcadores es una calibración visual provisional, no una certificación de ingeniería.

## Guía de uso desde la interfaz

### Consultar una inspección y sus tendencias

1. En el selector **INSPECTION** de la esquina superior derecha, elegir una fecha. Esa selección da contexto a Overview, Structural 3D, Crack analytics y Recommendations.
2. En **Inspections**, buscar por fecha o inspector con **Filter date or inspector**. El desplegable **All points** permite mostrar las lecturas de un SD concreto. Pulsar una fila o el icono del ojo para ver sus cuatro medidas, comentarios, procedencia y límites.
3. En **Crack analytics**, escoger el punto de interés y revisar la longitud RAW por fecha y horas de operación, los límites Caution/Danger, los márgenes y los cambios entre inspecciones. Las reparaciones documentadas aparecen en la serie; N/I sigue siendo una medición ausente.
4. En **Recommendations**, leer la acción propuesta, la prioridad, el valor RAW, los límites y la razón calculada para cada punto. Son reglas de apoyo a la decisión; una persona debe revisar y aprobar cualquier orden de trabajo.

### Registrar una inspección nueva

1. Abrir **Inspections → New inspection**.
2. Completar **Inspection date**, **Hour meter (h)** e **Inspector name / ID**. La fecha debe ser posterior a la última inspección registrada y el horómetro no puede ser menor que el último.
3. Para **SD-01, SD-02, SD-03 y SD-04**, escribir la longitud medida en milímetros. Si un punto no se pudo medir, marcar **N/I**. Un campo vacío no equivale a `0 mm`: `0` es una medición válida y N/I significa dato no disponible. Los comentarios son opcionales.
4. Pulsar **Save inspection**. La nueva campaña aparecerá en el historial y podrá elegirse en el selector **INSPECTION**. Overview, gráficas y recomendaciones se recalculan con ella. La aplicación no sobrescribe fechas históricas ni acepta una fecha duplicada.
5. Si se dispone de una foto o PDF, adjuntarlo después desde **Evidence** con el procedimiento siguiente.

### Crear y planificar una orden de trabajo

1. Elegir primero la inspección deseada en **INSPECTION** y abrir **Recommendations**. En la tarjeta del punto correspondiente, pulsar **Create work order**.
2. Revisar o editar **Intervention / work scope** y **Description**. Pulsar **Create PENDING order**. Esta acción crea un borrador pendiente; no registra una reparación realizada.
3. Abrir **Planning & work orders**. Buscar la orden y pulsar **Approve** solo tras la revisión humana.
4. Indicar **Scheduled date** y pulsar **Schedule**. Cuando corresponda, usar **Start** y **Complete** para registrar el avance. También se puede cancelar una orden abierta.
5. El icono **Show audit history** muestra las transiciones. Allí se pueden completar **Responsible** y **Observations** con **Save details**. Los contadores de estado y los filtros **All / Open only** ayudan a consultar el plan.

Las recomendaciones **no** pasan automáticamente a órdenes aprobadas, programadas o ejecutadas. La fecha de trabajo la introduce el usuario.

### Adjuntar evidencia

1. Abrir **Evidence → Select an image or PDF** y escoger un archivo **JPG, PNG, WEBP o PDF** de hasta **20 MB**.
2. En **Link to**, elegir **Inspection** o **Work order**. Para una inspección, seleccionar **Inspection date** e **Inspection point**. Para una orden, seleccionar **Work order**.
3. Añadir el **Context** del archivo y pulsar **Upload and link evidence**. El archivo aparecerá en **Uploaded evidence** y se podrá abrir desde allí.

Las referencias a imágenes presentes en el Excel son metadatos: las fotografías históricas originales no fueron entregadas y la aplicación no las presenta como archivos verificados.

### Ver los datos propios y borrar pruebas

En **Settings & calibration → Registros creados por el usuario** aparecen los contadores de inspecciones, órdenes y evidencias creadas en **ese navegador**. **Borrar registros locales** elimina **todos** esos registros nuevos, sus cambios de estado y los archivos adjuntos, tras pedir confirmación. La acción no tiene papelera ni recuperación dentro de la aplicación; las 25 inspecciones importadas permanecen disponibles. Si el navegador borra los datos del sitio, también se pierden los registros nuevos.

## Dónde se guardan los datos de la web

La versión publicada en GitHub Pages guarda las inspecciones nuevas, órdenes y su auditoría en el almacenamiento local del navegador; los archivos adjuntos se guardan en IndexedDB del mismo origen. **Persisten al recargar y al volver a abrir el sitio en ese navegador**, pero no se sincronizan entre navegadores, perfiles, dispositivos o evaluadores. La página no tiene cuentas ni una base de datos compartida. El historial validado se descarga como contenido de solo lectura del sitio.

Se comprobó en la web publicada que una inspección nueva, una orden programada y una imagen seguían presentes después de recargar. Luego se eliminaron con **Borrar registros locales** y, después de otra recarga, los contadores volvieron a cero y la última inspección histórica siguió seleccionada.

## Criterios de interpretación

- Fuente: `DATOSCRUDOS/EH4000_historial_grietas.xlsx`. La carga validada utiliza `outputs/maintenance/maintenance_features.csv`, `outputs/maintenance/zone_snapshot.csv` y las salidas QA vinculadas al hash SHA-256 del libro.
- `0 mm` es una medición disponible sin grieta detectable; **N/I** es una medición no disponible.
- `MEASUREMENT_TOLERANCE_MM = 10` se usa para interpretar cambios entre inspecciones. Los estados Normal/Alerta/Crítico se calculan con la longitud RAW y los límites oficiales, sin aplicar esa tolerancia.
- Un cambio desde la última medida válida anterior a N/I hasta la primera posterior se muestra como cambio a través de un intervalo incompleto, con advertencia. No es una observación consecutiva ni una tasa ordinaria.
- No se ejecutan predicciones, aprendizaje automático, imputación, suavizado ni interpolación. Las recomendaciones son heurísticas reproducibles y no equivalen a la aprobación de un ingeniero.
- El STL de suspensión se conserva como malla técnica de una pieza; sus unidades de origen no están documentadas y no es una malla cerrada. El GLB del camión proviene de una conversión del mod FS25 y sirve solo como contexto visual, no como geometría validada para los SD.

## Ejecutar el proyecto completo en Windows (desarrollo)

La versión con FastAPI y SQLite es una instalación local distinta de la web publicada. Con Anaconda o Miniconda, desde la raíz del proyecto:

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

Abrir `http://127.0.0.1:5173`; la documentación de la API está en `http://127.0.0.1:8000/docs`. Para compilar: `cd frontend; npm run build`. Para previsualizar una compilación local: `npm run preview -- --port 4173 --strictPort`. Si el servidor de desarrollo se detuvo, hay que volver a iniciarlo; `127.0.0.1` solo funciona en el equipo que lo ejecuta.

En esa instalación, `backend/eh4000_integrity.sqlite3` contiene los registros operativos y `backend/uploads/` los adjuntos. Se deben respaldar ambos antes de mover o reinstalar el proyecto. Las variables `EH4000_DB_PATH` y `EH4000_DATABASE_URL` permiten seleccionar otra base.

## Publicación

El workflow `.github/workflows/pages.yml` genera los datos iniciales desde una base temporal nueva con `scripts/export_static_demo.py`, compila React para GitHub Pages y publica `frontend/dist`. No incluye los registros creados en un navegador por un evaluador. El repositorio también conserva `Dockerfile`, `compose.yaml`, `compose.public.yaml` y `Caddyfile` para una instalación futura con servidor y almacenamiento compartido; **la entrega actual usa el enlace de GitHub Pages indicado arriba**.

El archivo `frontend/public/assets/hitachi_eh4000_fs25.glb` corresponde al mod FS25 facilitado para el contexto visual del camión. Antes de redistribuir ese recurso fuera de esta demostración académica conviene comprobar sus términos de uso.
