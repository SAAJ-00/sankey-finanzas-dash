# Sankey Finanzas Dash

Aplicacion Dash para visualizar flujo de ingresos, gastos y utilidad neta con un grafico Sankey editable.

## Caracteristicas

- Edicion interactiva de montos desde tabla.
- Agregar y eliminar items de ingreso y gasto.
- Recalculo automatico de gastos totales y utilidad neta.
- Visualizacion Sankey con orden de enlaces controlado.

## Requisitos

- Python 3.11+
- pip

## Instalacion

```bash
pip install -r requirements.txt
```

## Uso

Sin CSV (usa datos por defecto):

```bash
python sankey_dash_app.py
```

Con CSV:

```bash
python sankey_dash_app.py ruta/al/archivo.csv
```

Luego abre en tu navegador la URL que muestra Dash (normalmente http://127.0.0.1:8050).

## Formato esperado del CSV

Debe incluir estas columnas:

- origen
- destino
- monto_clp

Y debe contener nodos equivalentes a:

- ingresos_totales
- gastos_totales
- utilidad_neta

## Estructura

- sankey_dash_app.py: app principal.
- requirements.txt: dependencias Python.
- .gitignore: exclusiones de Git.
