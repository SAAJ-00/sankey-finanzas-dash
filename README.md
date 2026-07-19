# Sankey Finanzas Dash

Aplicacion Dash para visualizar flujo de ingresos, gastos y utilidad neta con un grafico Sankey editable.

## Caracteristicas

- Edicion interactiva de montos desde tabla.
- Agregar y eliminar items de ingreso y gasto.
- Recalculo automatico de gastos totales y utilidad neta.
- Visualizacion Sankey con orden de enlaces controlado.
- Version HTML/JavaScript standalone que funciona sin servidor.

## Requisitos

- Python 3.11+
- pip

## Instalacion

```bash
pip install -r requirements.txt
```

## Uso

### 0. Version HTML standalone (sin Python ni servidor)

Abre directamente `index.html` en cualquier navegador moderno.

Incluye:

- Datos por defecto equivalentes a `create_default_table()`.
- Tabla editable para montos y etiquetas.
- Botones para agregar o eliminar partidas.
- Recalculo automatico de `gastos_totales` y `utilidad_neta`.
- Validaciones visibles en pantalla.

### 1. Sin CSV (usa datos por defecto):

```bash
python sankey_dash_app.py
```

Luego abre en tu navegador la URL que muestra Dash (normalmente http://127.0.0.1:8050).

### 2. Con CSV:

```bash
python sankey_dash_app.py ruta/al/archivo.csv
```

Luego abre en tu navegador la URL que muestra Dash (normalmente http://127.0.0.1:8050).

#### 2.1 Formato esperado del CSV

Debe incluir estas columnas:

- origen
- destino
- monto_clp

Y debe contener nodos equivalentes a:

- ingresos_totales
- gastos_totales
- utilidad_neta

Ejemplo:

| origen           | destino          | monto_clp |
|:-----------------|:-----------------|:----------|
| ingreso_1        | ingresos_totales | 12345     |
| gasto_1          | gastos_totales   | 1234      |
| ingresos_totales | utilidad_neta    | 123       |


## Estructura

- index.html: version standalone en HTML/CSS/JavaScript con Plotly.js.
- plotly.min.js: bundle local de Plotly.js para que el HTML funcione sin red ni servidor.
- sankey_dash_app.py: app principal.
- requirements.txt: dependencias Python.
- .gitignore: exclusiones de Git.
