from pathlib import Path
import sys

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback_context, dash_table, dcc, html


STRUCTURAL_ROWS = [
    {"origen": "ingresos_totales", "destino": "gastos_totales", "monto_clp": 0, "row_kind": "structural"},
    {"origen": "gastos_totales", "destino": "utilidad_neta", "monto_clp": 0, "row_kind": "structural"},
]


def _normalize_label(label):
    return str(label).strip().lower().replace(" ", "_")


def _find_terminal_roles(terminal_labels):
    gasto_idx = None
    utilidad_idx = None

    for idx, label in enumerate(terminal_labels):
        normalized = _normalize_label(label)
        if gasto_idx is None and any(word in normalized for word in ["gasto", "egreso", "cost", "costo"]):
            gasto_idx = idx
        if utilidad_idx is None and any(word in normalized for word in ["utilidad", "neta", "ganancia", "profit"]):
            utilidad_idx = idx

    if gasto_idx is None or utilidad_idx is None:
        raise ValueError(
            "No pude identificar los dos nodos terminales esperados. "
            "Asegurate de que existan terminales con nombres similares a 'gastos_totales' y 'utilidad_neta'."
        )

    if gasto_idx == utilidad_idx:
        raise ValueError("Los nodos terminales de gasto y utilidad quedaron mapeados al mismo nodo.")

    return gasto_idx, utilidad_idx


def _find_special_labels(labels):
    normalized_map = {_normalize_label(label): label for label in labels}

    def find_label(priority_groups):
        for group in priority_groups:
            for candidate in group:
                if candidate in normalized_map:
                    return normalized_map[candidate]

        for normalized, original in normalized_map.items():
            for group in priority_groups:
                if any(token in normalized for token in group):
                    return original
        return None

    ingresos_label = find_label(
        [
            ["ingresos_totales", "ingreso_total", "total_ingresos", "total_ingreso"],
            ["ingresos", "ingreso", "revenue_total", "total_revenue"],
            ["revenue"],
        ]
    )
    gastos_label = find_label(
        [
            ["gastos_totales", "gasto_total", "egresos_totales", "egreso_total", "total_gastos"],
            ["gastos", "gasto", "egresos", "egreso", "costos_totales", "costo_total"],
            ["cost", "costo"],
        ]
    )
    utilidad_label = find_label(
        [
            ["utilidad_neta", "neta_utilidad", "ganancia_neta", "net_profit"],
            ["utilidad", "ganancia", "profit", "neta"],
        ]
    )

    if ingresos_label is None or gastos_label is None or utilidad_label is None:
        raise ValueError(
            "No pude identificar ingresos_totales, gastos_totales y utilidad_neta en la tabla. "
            "Revisa que esos nodos existan con nombres similares."
        )

    return ingresos_label, gastos_label, utilidad_label


def prepare_flow_table(df, source_col="origen", target_col="destino", value_col="monto_clp"):
    required_columns = [source_col, target_col, value_col]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Faltan columnas requeridas en la tabla: {missing_columns}")

    working_df = df.copy()
    working_df[value_col] = pd.to_numeric(working_df[value_col], errors="coerce")

    all_labels = pd.unique(working_df[[source_col, target_col]].values.ravel("K")).tolist()
    ingresos_label, gastos_label, utilidad_label = _find_special_labels(all_labels)

    editable_income_mask = working_df[target_col] == ingresos_label
    expense_out_mask = (working_df[source_col] == gastos_label) & (working_df[target_col] != utilidad_label)
    expense_in_mask = (working_df[target_col] == gastos_label) & (working_df[source_col] != ingresos_label)
    editable_expense_mask = expense_out_mask | expense_in_mask
    total_expense_mask = (working_df[source_col] == ingresos_label) & (working_df[target_col] == gastos_label)
    utilidad_mask = (working_df[source_col] == gastos_label) & (working_df[target_col] == utilidad_label)
    editable_mask = editable_income_mask | editable_expense_mask

    if working_df.loc[editable_mask, value_col].isna().any():
        invalid_rows = working_df.index[editable_mask & working_df[value_col].isna()].tolist()
        raise ValueError(f"Hay valores no numericos en filas editables: {invalid_rows}")

    if (working_df.loc[editable_mask, value_col] <= 0).any():
        invalid_rows = working_df.index[editable_mask & (working_df[value_col] <= 0)].tolist()
        raise ValueError(f"Los montos editables deben ser mayores que 0. Filas invalidas: {invalid_rows}")

    if working_df.loc[editable_income_mask, value_col].sum() <= 0:
        raise ValueError("La suma de los ingresos editables debe ser mayor que 0.")

    if not editable_expense_mask.any():
        raise ValueError("Debe existir al menos una fila editable de gasto (origen o destino gastos_totales).")

    total_expense_rows = working_df.index[total_expense_mask].tolist()
    if len(total_expense_rows) != 1:
        raise ValueError(
            "Debe existir exactamente una fila con origen ingresos_totales y destino gastos_totales."
        )

    utilidad_rows = working_df.index[utilidad_mask].tolist()
    if len(utilidad_rows) != 1:
        raise ValueError(
            "Debe existir exactamente una fila con origen gastos_totales y destino utilidad_neta."
        )

    total_ingresos = working_df.loc[editable_income_mask, value_col].sum()
    total_gastos = working_df.loc[editable_expense_mask, value_col].sum()
    utilidad_value = total_ingresos - total_gastos

    if utilidad_value < 0:
        raise ValueError(
            "La utilidad_neta calculada no puede ser negativa. "
            f"Ingresos: {total_ingresos:,.2f}. Gastos: {total_gastos:,.2f}."
        )

    working_df.at[total_expense_rows[0], value_col] = total_gastos
    working_df.at[utilidad_rows[0], value_col] = utilidad_value
    return working_df


def build_sankey_input_df(df, source_col="origen", target_col="destino", value_col="monto_clp"):
    prepared_df = prepare_flow_table(df, source_col, target_col, value_col)
    all_labels = pd.unique(prepared_df[[source_col, target_col]].values.ravel("K")).tolist()
    ingresos_label, gastos_label, utilidad_label = _find_special_labels(all_labels)

    sankey_rows = []

    income_rows = prepared_df[prepared_df[target_col] == ingresos_label]
    for row in income_rows.itertuples(index=False):
        sankey_rows.append(
            {source_col: getattr(row, source_col), target_col: ingresos_label, value_col: getattr(row, value_col)}
        )

    expense_rows = prepared_df[
        (
            (prepared_df[source_col] == gastos_label) & (prepared_df[target_col] != utilidad_label)
        )
        |
        (
            (prepared_df[target_col] == gastos_label) & (prepared_df[source_col] != ingresos_label)
        )
    ]
    for row in expense_rows.itertuples(index=False):
        row_source = getattr(row, source_col)
        row_target = getattr(row, target_col)
        expense_label = row_target if row_source == gastos_label else row_source
        expense_value = getattr(row, value_col)
        sankey_rows.append({source_col: ingresos_label, target_col: expense_label, value_col: expense_value})
        sankey_rows.append({source_col: expense_label, target_col: gastos_label, value_col: expense_value})

    utilidad_value = prepared_df.loc[
        (prepared_df[source_col] == gastos_label) & (prepared_df[target_col] == utilidad_label),
        value_col,
    ].iloc[0]
    sankey_rows.append({source_col: ingresos_label, target_col: utilidad_label, value_col: utilidad_value})

    sankey_df = pd.DataFrame(sankey_rows)
    sankey_df["_link_order"] = sankey_df.apply(
        lambda row: (
            0
            if row[source_col] == ingresos_label and row[target_col] != utilidad_label
            else 1
            if row[source_col] != ingresos_label and row[target_col] == gastos_label
            else 2
            if row[source_col] == ingresos_label and row[target_col] == utilidad_label
            else 3
        ),
        axis=1,
    )
    sankey_df["_target_sort"] = sankey_df[target_col].map(_normalize_label)
    sankey_df["_source_sort"] = sankey_df[source_col].map(_normalize_label)
    sankey_df = sankey_df.sort_values(
        ["_link_order", "_target_sort", "_source_sort", value_col],
        ascending=[True, True, True, False],
        kind="stable",
    ).drop(columns=["_link_order", "_target_sort", "_source_sort"])
    sankey_df[value_col] = pd.to_numeric(sankey_df[value_col], errors="coerce")
    return prepared_df, sankey_df


def _build_node_positions(df, source_col, target_col, labels, terminal_labels, value_col):
    outgoing = {label: [] for label in labels}
    incoming = {label: [] for label in labels}
    outgoing_value = {label: 0 for label in labels}
    incoming_value = {label: 0 for label in labels}

    for row in df.itertuples(index=False):
        source_label = getattr(row, source_col)
        target_label = getattr(row, target_col)
        flow_value = getattr(row, value_col)
        outgoing[source_label].append(target_label)
        incoming[target_label].append(source_label)
        outgoing_value[source_label] += flow_value
        incoming_value[target_label] += flow_value

    terminals = set(terminal_labels)
    gasto_idx, utilidad_idx = _find_terminal_roles(terminal_labels)
    gasto_label = terminal_labels[gasto_idx]
    utilidad_label = terminal_labels[utilidad_idx]

    memo_terminal_group = {}

    def terminal_group(label):
        if label in memo_terminal_group:
            return memo_terminal_group[label]
        if label == gasto_label:
            memo_terminal_group[label] = 0
            return 0
        if label == utilidad_label:
            memo_terminal_group[label] = 1
            return 1

        child_groups = {terminal_group(child) for child in outgoing.get(label, [])}
        memo_terminal_group[label] = 0 if child_groups == {0} else 1 if child_groups == {1} else 0.5
        return memo_terminal_group[label]

    memo_level = {}

    def level(label):
        if label in memo_level:
            return memo_level[label]
        if label in terminals:
            memo_level[label] = 0
            return 0
        next_levels = [level(child) for child in outgoing.get(label, [])]
        memo_level[label] = (max(next_levels) + 1) if next_levels else 1
        return memo_level[label]

    node_levels_from_end = {label: level(label) for label in labels}
    max_level = max(node_levels_from_end.values()) if node_levels_from_end else 1

    layers = {}
    for label in labels:
        layer_idx = max_level - node_levels_from_end[label]
        layers.setdefault(layer_idx, []).append(label)

    x_positions = {}
    y_positions = {}
    layer_counts = {}

    def direct_to_terminal(label):
        children = outgoing.get(label, [])
        return bool(children) and all(child in terminals for child in children)

    for layer_idx, layer_labels in sorted(layers.items()):
        layer_counts[layer_idx] = len(layer_labels)

        def parent_center(item):
            parents = incoming.get(item, [])
            if not parents:
                return 0.5
            parent_positions = [y_positions[parent] for parent in parents if parent in y_positions]
            return sum(parent_positions) / len(parent_positions) if parent_positions else 0.5

        layer_labels.sort(
            key=lambda item: (
                terminal_group(item),
                direct_to_terminal(item),
                parent_center(item),
                -max(incoming_value.get(item, 0), outgoing_value.get(item, 0)),
                _normalize_label(item),
            )
        )

        count = len(layer_labels)
        x_value = 0.01 if max_level == 0 else 0.01 + (0.98 * layer_idx / max_level)

        if count == 1:
            y_values = [0.5]
        else:
            top = 0.12
            bottom = 0.88
            step = (bottom - top) / (count - 1)
            y_values = [top + step * idx for idx in range(count)]

        for label, y_value in zip(layer_labels, y_values):
            x_positions[label] = x_value
            y_positions[label] = y_value

    x_positions[gasto_label] = 0.99
    y_positions[gasto_label] = 0.2
    x_positions[utilidad_label] = 0.99
    y_positions[utilidad_label] = 0.8

    max_nodes_in_layer = max(layer_counts.values()) if layer_counts else len(labels)
    return [x_positions[label] for label in labels], [y_positions[label] for label in labels], max_nodes_in_layer


def load_table_from_csv(csv_path, source_col="origen", target_col="destino", value_col="monto_clp"):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {csv_path}")

    df = pd.read_csv(csv_path)
    required = [source_col, target_col, value_col]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas requeridas: {missing}. Columnas disponibles: {list(df.columns)}"
        )

    return df[required].copy()


def _base_table_with_row_kinds(df):
    working_df = df.copy()
    if "row_kind" not in working_df.columns:
        working_df["row_kind"] = "editable"

    if ((working_df["origen"] == "ingresos_totales") & (working_df["destino"] == "gastos_totales")).any():
        working_df.loc[
            (working_df["origen"] == "ingresos_totales") & (working_df["destino"] == "gastos_totales"),
            "row_kind",
        ] = "structural"

    if ((working_df["origen"] == "gastos_totales") & (working_df["destino"] == "utilidad_neta")).any():
        working_df.loc[
            (working_df["origen"] == "gastos_totales") & (working_df["destino"] == "utilidad_neta"),
            "row_kind",
        ] = "structural"

    return working_df


def create_default_table():
    return pd.DataFrame(
        [
            {"origen": "ventas_productos", "destino": "ingresos_totales", "monto_clp": 4200000, "row_kind": "editable"},
            {"origen": "comisiones_mercadolibre", "destino": "ingresos_totales", "monto_clp": 50000, "row_kind": "editable"},
            *STRUCTURAL_ROWS,
            {"origen": "gastos_totales", "destino": "compra_insumos", "monto_clp": 2100000, "row_kind": "editable"},
            {"origen": "gastos_totales", "destino": "arriendo_local", "monto_clp": 500000, "row_kind": "editable"},
            {"origen": "gastos_totales", "destino": "gastos_luz_agua", "monto_clp": 80000, "row_kind": "editable"},
            {"origen": "gastos_totales", "destino": "mobiliario", "monto_clp": 120000, "row_kind": "editable"},
            {"origen": "gastos_totales", "destino": "seguro_robos_incendio", "monto_clp": 150000, "row_kind": "editable"},
            {"origen": "gastos_totales", "destino": "publicidad", "monto_clp": 100000, "row_kind": "editable"},
        ]
    )


def build_sankey_from_df(
    df,
    source_col="origen",
    target_col="destino",
    value_col="monto_clp",
    title="Sankey Ingresos y Gastos",
):
    _, working_df = build_sankey_input_df(df, source_col, target_col, value_col)
    all_labels = pd.unique(working_df[[source_col, target_col]].values.ravel("K")).tolist()
    ingresos_label, _, utilidad_label = _find_special_labels(all_labels)

    if working_df[value_col].isna().any():
        invalid_rows = working_df[working_df[value_col].isna()].index.tolist()
        raise ValueError(f"Hay valores no numericos en '{value_col}' en las filas: {invalid_rows}")

    if (working_df[value_col] <= 0).any():
        invalid_rows = working_df[working_df[value_col] <= 0].index.tolist()
        raise ValueError(f"Todos los montos del Sankey deben ser mayores que 0. Filas invalidas: {invalid_rows}")

    grouped_df = working_df.groupby([source_col, target_col], as_index=False)[value_col].sum()
    grouped_df["_utilidad_last"] = (
        (grouped_df[source_col] == ingresos_label) & (grouped_df[target_col] == utilidad_label)
    ).astype(int)
    grouped_df = grouped_df.sort_values(
        ["_utilidad_last", value_col],
        ascending=[True, False],
        kind="stable",
    ).drop(columns=["_utilidad_last"])

    labels = pd.unique(grouped_df[[source_col, target_col]].values.ravel("K")).tolist()
    node_index = {label: idx for idx, label in enumerate(labels)}
    source_nodes = set(grouped_df[source_col])
    terminal_labels = [label for label in labels if label not in source_nodes]

    if len(terminal_labels) != 2:
        raise ValueError(
            "Se esperaban exactamente 2 nodos terminales en el Sankey interno. "
            f"Se detectaron {len(terminal_labels)}: {terminal_labels}"
        )

    source = grouped_df[source_col].map(node_index).tolist()
    target = grouped_df[target_col].map(node_index).tolist()
    value = grouped_df[value_col].tolist()
    node_x, node_y, max_nodes_in_layer = _build_node_positions(
        grouped_df, source_col, target_col, labels, terminal_labels, value_col
    )

    gasto_idx, utilidad_idx = _find_terminal_roles(terminal_labels)
    gasto_label = terminal_labels[gasto_idx]
    utilidad_label = terminal_labels[utilidad_idx]

    node_colors = [
        "rgba(214, 39, 40, 0.95)" if label == gasto_label
        else "rgba(44, 160, 44, 0.95)" if label == utilidad_label
        else "rgba(160, 160, 160, 0.22)"
        for label in labels
    ]

    gasto_node = node_index[gasto_label]
    utilidad_node = node_index[utilidad_label]
    link_colors = []
    for target_idx in target:
        if target_idx == gasto_node:
            link_colors.append("rgba(220, 90, 90, 0.35)")
        elif target_idx == utilidad_node:
            link_colors.append("rgba(90, 180, 90, 0.35)")
        else:
            link_colors.append("rgba(160, 160, 160, 0.20)")

    node_thickness = max(10, min(20, int(240 / max(max_nodes_in_layer, 1))))
    node_pad = max(12, min(24, int(320 / max(max_nodes_in_layer, 1))))
    figure_height = max(700, 70 * max_nodes_in_layer)

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node=dict(
                    label=labels,
                    pad=node_pad,
                    thickness=node_thickness,
                    color=node_colors,
                    x=node_x,
                    y=node_y,
                    line=dict(color="rgba(0, 0, 0, 0.25)", width=0.5),
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value,
                    color=link_colors,
                    hovertemplate="%{source.label} -> %{target.label}<br>Monto: %{value:,.2f}<extra></extra>",
                ),
            )
        ]
    )

    fig.update_layout(title_text=title, font_size=12, height=figure_height)
    return fig


def build_error_figure(message):
    fig = go.Figure()
    fig.update_layout(
        height=500,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(
                text=message,
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=15, color="#b42318"),
            )
        ],
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def create_app(initial_df):
    initial_df = _base_table_with_row_kinds(initial_df)
    prepared_df = prepare_flow_table(initial_df)
    all_labels = pd.unique(prepared_df[["origen", "destino"]].values.ravel("K")).tolist()
    ingresos_label, gastos_label, utilidad_label = _find_special_labels(all_labels)
    app = Dash(__name__)

    app.layout = html.Div(
        [
            html.H2("Sankey interactivo de ingresos y gastos", style={"fontFamily": "Segoe UI"}),
            html.P(
                "La tabla visible replica la estructura del CSV original. Puedes editar, agregar o eliminar partidas con destino ingresos_totales o gastos_totales; los totales y la utilidad se recalculan automaticamente.",
                style={"marginBottom": "16px", "fontFamily": "Segoe UI"},
            ),
            html.Div(
                [
                    html.Button("Agregar item de ingreso", id="add-income-item", n_clicks=0, style={"marginRight": "8px"}),
                    html.Button("Agregar item de gasto", id="add-expense-item", n_clicks=0),
                ],
                style={"marginBottom": "12px"},
            ),
            html.Div(id="validation-message", style={"color": "#b42318", "marginBottom": "12px", "fontFamily": "Segoe UI"}),
            dash_table.DataTable(
                id="flow-table",
                data=prepared_df.to_dict("records"),
                columns=[
                    {"name": "origen", "id": "origen", "editable": True},
                    {"name": "destino", "id": "destino", "editable": False},
                    {"name": "monto_clp", "id": "monto_clp", "editable": True, "type": "numeric"},
                ],
                editable=True,
                row_deletable=True,
                sort_action="native",
                page_action="none",
                style_table={"overflowX": "auto", "maxHeight": "420px", "overflowY": "auto"},
                style_cell={"padding": "10px", "fontFamily": "Segoe UI", "fontSize": 13},
                style_header={"fontWeight": "bold", "backgroundColor": "#f3f4f6"},
                style_data_conditional=[
                    {
                        "if": {"column_id": "delete"},
                        "backgroundColor": "#b91c1c",
                        "color": "#ffffff",
                        "fontWeight": "bold",
                        "border": "1px solid #7f1d1d",
                    },
                    {
                        "if": {
                            "column_id": "monto_clp",
                            "filter_query": f"{{destino}} = '{ingresos_label}' || ({{origen}} = '{gastos_label}' && {{destino}} != '{utilidad_label}') || ({{destino}} = '{gastos_label}' && {{origen}} != '{ingresos_label}')",
                        },
                        "backgroundColor": "#fff8e1",
                    },
                    {
                        "if": {
                            "filter_query": f"({{origen}} = '{ingresos_label}' && {{destino}} = '{gastos_label}') || ({{origen}} = '{gastos_label}' && {{destino}} = '{utilidad_label}')",
                        },
                        "backgroundColor": "#eef2f7",
                        "color": "#475569",
                    },
                    {
                        "if": {
                            "column_id": "monto_clp",
                            "filter_query": f"{{origen}} = '{ingresos_label}' && {{destino}} = '{gastos_label}'",
                        },
                        "backgroundColor": "#e5e7eb",
                        "color": "#6b7280",
                    },
                    {
                        "if": {
                            "column_id": "monto_clp",
                            "filter_query": f"{{origen}} = '{gastos_label}' && {{destino}} = '{utilidad_label}'",
                        },
                        "backgroundColor": "#dcfce7",
                        "color": "#166534",
                    },
                ],
            ),
            dcc.Graph(id="sankey-graph", style={"marginTop": "20px"}),
        ],
        style={"maxWidth": "1400px", "margin": "24px auto", "padding": "0 20px"},
    )

    @app.callback(
        Output("flow-table", "data"),
        Output("sankey-graph", "figure"),
        Output("validation-message", "children"),
        Input("add-income-item", "n_clicks"),
        Input("add-expense-item", "n_clicks"),
        Input("flow-table", "data_timestamp"),
        State("flow-table", "data"),
    )
    def update_graph(_, __, ___, rows):
        trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
        rows = rows or []
        rows_df = pd.DataFrame(rows)

        if rows_df.empty:
            rows_df = pd.DataFrame(columns=["origen", "destino", "monto_clp", "row_kind"])

        if "row_kind" not in rows_df.columns:
            rows_df["row_kind"] = "editable"

        rows_df = rows_df[~((rows_df["origen"] == "ingresos_totales") & (rows_df["destino"] == "gastos_totales"))]
        rows_df = rows_df[~((rows_df["origen"] == "gastos_totales") & (rows_df["destino"] == "utilidad_neta"))]

        if trigger_id == "add-income-item":
            rows_df = pd.concat(
                [
                    rows_df,
                    pd.DataFrame(
                        [{"origen": "nuevo_ingreso", "destino": ingresos_label, "monto_clp": 1, "row_kind": "editable"}]
                    ),
                ],
                ignore_index=True,
            )
        elif trigger_id == "add-expense-item":
            rows_df = pd.concat(
                [
                    rows_df,
                    pd.DataFrame(
                        [{"origen": "nuevo_gasto", "destino": gastos_label, "monto_clp": 1, "row_kind": "editable"}]
                    ),
                ],
                ignore_index=True,
            )

        rows_df = pd.concat([rows_df, pd.DataFrame(STRUCTURAL_ROWS)], ignore_index=True)
        rows = rows_df.to_dict("records")

        try:
            prepared = prepare_flow_table(rows_df)
            fig = build_sankey_from_df(prepared)
            return prepared.to_dict("records"), fig, ""
        except Exception as exc:
            return rows, build_error_figure(str(exc)), str(exc)

    return app


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        initial_df = load_table_from_csv(csv_path)
    else:
        initial_df = create_default_table()

    app = create_app(initial_df)
    app.run(debug=True)
