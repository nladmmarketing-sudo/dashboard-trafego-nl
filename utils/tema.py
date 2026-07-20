"""Tema visual do dashboard — design system da agência (canvas branco,
esmeralda como acento de UI) + paleta de gráficos validada para CVD.

Paleta categórica validada (adjacente e all-pairs) em 2026-07-20 com o
validador da skill dataviz — não trocar cores nem ordem sem revalidar.
Amarelo e magenta ficam abaixo de 3:1 sobre branco: por isso todo gráfico
que os usa leva rótulo direto de valor e tabela de dados disponível.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ── Cores de UI (DESIGN.md da agência) ───────────────────────────────
ESMERALDA = "#3ecf8e"
ESMERALDA_DEEP = "#24b47e"
INK = "#171717"
INK_MUTE = "#707070"
INK_MUTE_2 = "#9a9a9a"
CANVAS = "#ffffff"
CANVAS_SOFT = "#fafafa"
HAIRLINE = "#dfdfdf"
HAIRLINE_COOL = "#ededed"

# ── Paleta categórica de canais (ordem fixa = mecanismo de segurança CVD)
CORES_CANAIS = {
    "Meta Ads": "#2a78d6",
    "Google Ads": "#eda100",
    "Portais": "#4a3aa7",
    "Site NL": "#008300",
    "Direto/Outros": "#e87ba4",
}
ORDEM_CANAIS = list(CORES_CANAIS.keys())

# Série única (magnitude genérica): azul slot 1
COR_SERIE = "#2a78d6"
# Rampa sequencial (claro → escuro) para funil/heatmap
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]

CORES_PLATAFORMA = {
    "Meta Ads": CORES_CANAIS["Meta Ads"],
    "Google Ads": CORES_CANAIS["Google Ads"],
}


def registrar_template_plotly() -> None:
    """Template Plotly do dashboard: grid recessivo, Inter, hover pt-BR."""
    template = go.layout.Template(
        layout=go.Layout(
            font=dict(
                family="Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif",
                color=INK,
                size=13,
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=list(CORES_CANAIS.values()),
            separators=",.",  # decimal vírgula, milhar ponto (pt-BR)
            margin=dict(l=8, r=8, t=36, b=8),
            hoverlabel=dict(
                bgcolor=CANVAS,
                bordercolor=HAIRLINE,
                font=dict(family="Inter, sans-serif", color=INK, size=13),
            ),
            xaxis=dict(
                gridcolor=HAIRLINE_COOL,
                linecolor=HAIRLINE,
                zerolinecolor=HAIRLINE,
                tickcolor=HAIRLINE,
                title_font=dict(size=12, color=INK_MUTE),
                tickfont=dict(size=12, color=INK_MUTE),
            ),
            yaxis=dict(
                gridcolor=HAIRLINE_COOL,
                linecolor="rgba(0,0,0,0)",
                zerolinecolor=HAIRLINE,
                tickcolor="rgba(0,0,0,0)",
                title_font=dict(size=12, color=INK_MUTE),
                tickfont=dict(size=12, color=INK_MUTE),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                font=dict(size=12, color=INK),
            ),
            title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
        )
    )
    pio.templates["nl_trafego"] = template
    pio.templates.default = "nl_trafego"


def injetar_css() -> None:
    """Inter + tokens do DESIGN.md aplicados no chrome do Streamlit."""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"], .stApp, p, div, span, label {
    font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
.stApp { background: #ffffff; }

h1, h2, h3 { font-weight: 500 !important; letter-spacing: -0.4px; color: #171717; }

/* Cards de métrica: hairline + radius 12 (card-feature-light) */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #dfdfdf;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
div[data-testid="stMetric"] label { color: #707070 !important; font-size: 13px; }
div[data-testid="stMetricValue"] { font-weight: 500; letter-spacing: -0.4px; font-size: 1.65rem !important; }

/* Abas */
button[data-baseweb="tab"] { font-weight: 500; }

/* Sidebar off-white com hairline */
section[data-testid="stSidebar"] {
    background: #fafafa;
    border-right: 1px solid #ededed;
}

/* Botões: radius 6px, verde com texto ink (assinatura do design system) */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 6px;
    border: 1px solid #c7c7c7;
    font-weight: 500;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
    background: #3ecf8e;
    color: #171717;
    border: none;
}
.stButton > button[kind="primary"]:hover { background: #24b47e; color: #171717; }

/* Tabelas mais discretas */
div[data-testid="stDataFrame"] { border: 1px solid #ededed; border-radius: 8px; }

/* Menu padrão do Streamlit fora do caminho */
#MainMenu, footer { visibility: hidden; }
</style>
""",
        unsafe_allow_html=True,
    )
