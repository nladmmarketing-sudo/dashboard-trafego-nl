"""Modelo 1 — Visão Geral de Performance (o dia a dia do gestor e da equipe).

Duas metades:
  1. Mídia paga (Meta / Google) — inspirado no relatório V4: scorecards com
     tendência, funil de tráfego, eficiência (CTR/CPC/CPM/CPR), série de
     resultados e ranking de campanhas.
  2. Captação no CRM (Jetimob) — leads reais, canais, origens e bairros.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, delta_pct, num, num_compacto, pct


# ── Helpers de UI ────────────────────────────────────────────────────

def _sparkline(valores, cor: str, altura: int = 56) -> go.Figure:
    """Mini-gráfico de tendência sem eixos, para os scorecards."""
    fig = go.Figure(
        go.Scatter(
            y=list(valores),
            mode="lines",
            line=dict(color=cor, width=2, shape="spline"),
            fill="tozeroy",
            fillcolor=tema.hex_rgba(cor, 0.10),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=altura,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _scorecard(col, titulo, valor, delta, serie, cor, ajuda=None, delta_bom_sobe=True):
    """Card no estilo V4: número + variação + sparkline."""
    with col:
        st.metric(titulo, valor, delta=delta, help=ajuda,
                  delta_color="normal" if delta_bom_sobe else "inverse")
        st.plotly_chart(_sparkline(serie, cor), width="stretch",
                        config={"displayModeBar": False})


def _pct_funil(frac: float) -> str:
    """Percentual do funil: 1 casa quando < 10% (senão '0%' apaga a etapa)."""
    p = frac * 100
    return f"{p:.1f}%".replace(".", ",") if p < 10 else f"{p:.0f}%"


def _serie_diaria(df: pd.DataFrame, col_dia: str, ini, fim, col_valor: str | None = None) -> pd.Series:
    """Agrega por dia e preenche dias sem registro com zero. Retorna Series indexada por data."""
    idx = pd.date_range(ini, fim, freq="D").date
    if df is None or df.empty:
        return pd.Series([0] * len(idx), index=idx)
    s = df.groupby(col_dia)[col_valor].sum() if col_valor else df.groupby(col_dia).size()
    return s.reindex(idx, fill_value=0)


def _ads_do_periodo(ads, ini, fim, canais):
    if ads is None:
        return None
    plataformas = [c for c in canais if c in ("Meta Ads", "Google Ads")]
    df = dados.filtrar_periodo(ads, "dia", ini, fim)
    if df is None or df.empty:
        return df
    return df[df["plataforma"].isin(plataformas)] if plataformas else df.iloc[0:0]


# ── Seção 1: Mídia paga (estilo V4) ──────────────────────────────────

def _secao_midia(ctx):
    ini, fim, canais = ctx["ini"], ctx["fim"], ctx["canais"]
    ini_ant, fim_ant = dados.janela_anterior(ini, fim)

    ads_per = _ads_do_periodo(ctx["ads"], ini, fim, canais)
    ads_ant = _ads_do_periodo(ctx["ads"], ini_ant, fim_ant, canais)
    tem_ads = ads_per is not None and not ads_per.empty

    st.markdown("#### Mídia paga — Meta / Google Ads")

    if ctx["ads"] is None:
        st.info(
            "**Investimento ainda não conectado.** Rode `sql/01_trafego_pago_schema.sql` no "
            "Supabase e depois `sync/sync_meta_ads.py` (ou lance manualmente na aba Executivo). "
            "Para ver o layout já preenchido, rode local com `DEMO_ADS=1`.",
            icon="🔌",
        )
    elif not tem_ads:
        st.info("**Sem investimento no período selecionado.** Rode o sync do Meta ou lance manual "
                "na aba Executivo.", icon="💸")

    # Agregados do período
    def soma(df, col):
        return float(df[col].sum()) if df is not None and not df.empty else 0.0

    spend = soma(ads_per, "spend")
    impress = soma(ads_per, "impressoes")
    alcance = soma(ads_per, "alcance")
    cliques = soma(ads_per, "cliques_link") or soma(ads_per, "cliques")
    leads_ads = soma(ads_per, "leads")
    mensagens = soma(ads_per, "mensagens")
    video = soma(ads_per, "video_plays")
    resultados = leads_ads + mensagens

    spend_a = soma(ads_ant, "spend")
    result_a = soma(ads_ant, "leads") + soma(ads_ant, "mensagens")
    cliques_a = soma(ads_ant, "cliques_link") or soma(ads_ant, "cliques")
    alcance_a = soma(ads_ant, "alcance")
    video_a = soma(ads_ant, "video_plays")

    # Séries diárias para os sparklines
    sp = _serie_diaria(ads_per, "dia", ini, fim, "spend")
    sr_leads = _serie_diaria(ads_per, "dia", ini, fim, "leads")
    sr_msg = _serie_diaria(ads_per, "dia", ini, fim, "mensagens")
    sr_result = sr_leads + sr_msg
    sr_cliques = _serie_diaria(ads_per, "dia", ini, fim, "cliques_link")
    sr_alcance = _serie_diaria(ads_per, "dia", ini, fim, "alcance")
    sr_video = _serie_diaria(ads_per, "dia", ini, fim, "video_plays")

    def v(x, fmt):
        return fmt(x) if tem_ads else "—"

    # Linha 1 — scorecards com tendência
    c1, c2, c3, c4, c5 = st.columns(5)
    _scorecard(c1, "Investimento", v(spend, lambda x: brl(x, 2)),
               delta_pct(spend, spend_a), sp, tema.COR_INVESTIMENTO,
               ajuda="Gasto total em anúncios no período", delta_bom_sobe=False)
    _scorecard(c2, "Resultados", v(resultados, lambda x: num(x)),
               delta_pct(resultados, result_a), sr_result, tema.COR_RESULTADO,
               ajuda="Leads de formulário + conversas iniciadas (WhatsApp/Direct)")
    _scorecard(c3, "Cliques no link", v(cliques, lambda x: num(x)),
               delta_pct(cliques, cliques_a), sr_cliques, tema.COR_CLIQUES)
    _scorecard(c4, "Alcance", v(alcance, lambda x: num(x)),
               delta_pct(alcance, alcance_a), sr_alcance, tema.COR_ALCANCE,
               ajuda="Pessoas únicas alcançadas")
    _scorecard(c5, "Video plays", v(video, lambda x: num(x)),
               delta_pct(video, video_a), sr_video, tema.COR_VIDEO)

    # Linha 2 — eficiência (métricas de custo/qualidade)
    ctr = (cliques / impress) if impress else None
    cpc = (spend / cliques) if cliques else None
    cpm = (spend / impress * 1000) if impress else None
    cpr = (spend / resultados) if resultados else None
    freq = (impress / alcance) if alcance else None
    taxa_result = (resultados / cliques) if cliques else None

    e1, e2, e3, e4, e5, e6 = st.columns(6)
    e1.metric("CTR", v(ctr, lambda x: pct(x, 2)), help="Cliques ÷ impressões")
    e2.metric("CPC", v(cpc, lambda x: brl(x, 2)), help="Custo por clique no link")
    e3.metric("CPM", v(cpm, lambda x: brl(x, 2)), help="Custo por mil impressões")
    e4.metric("CPR", v(cpr, lambda x: brl(x, 2)), help="Custo por resultado (lead/conversa)")
    e5.metric("Frequência", v(freq, lambda x: f"{x:.2f}".replace(".", ",")),
              help="Média de vezes que cada pessoa viu o anúncio. Acima de ~3-4 = saturação.")
    e6.metric("Result./clique", v(taxa_result, lambda x: pct(x, 2)),
              help="Taxa de resultado: resultados ÷ cliques no link")

    st.write("")

    # Linha 3 — Funil de tráfego + série de resultados
    col_funil, col_serie = st.columns([1, 1.25])

    with col_funil:
        if tem_ads:
            etapas = ["Impressões", "Alcance", "Cliques", "Resultados"]
            valores = [impress, alcance, cliques, resultados]
            base = valores[0] or 1
            rotulos = [
                f"{num_compacto(val)}  ·  {_pct_funil(val / base)}"
                for val in valores
            ]
            cores = [tema.RAMPA_AZUL[1], tema.RAMPA_AZUL[3], tema.RAMPA_AZUL[4], tema.RAMPA_AZUL[6]]
            fig = go.Figure(
                go.Funnel(
                    y=etapas, x=valores,
                    text=rotulos, textinfo="text",
                    textfont=dict(size=13),
                    marker=dict(color=cores),
                    connector=dict(line=dict(color=tema.HAIRLINE, width=1)),
                    hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
                )
            )
            fig.update_layout(title="Funil de tráfego", height=340, showlegend=False,
                              margin=dict(l=8, r=8, t=40, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            _placeholder("Funil de tráfego aparece aqui após o primeiro sync", 340)

    with col_serie:
        if tem_ads:
            dias = list(sr_result.index)
            cpr_dia = [
                (sp.iloc[i] / sr_result.iloc[i]) if sr_result.iloc[i] else None
                for i in range(len(dias))
            ]
            fig = go.Figure(
                go.Bar(
                    x=dias, y=sr_result.values,
                    marker=dict(color=tema.COR_RESULTADO, cornerradius=3),
                    customdata=[[c if c is not None else 0] for c in cpr_dia],
                    hovertemplate="%{x|%d/%m}<br><b>%{y} resultados</b>"
                                  "<br>CPR: R$ %{customdata[0]:,.2f}<extra></extra>",
                )
            )
            fig.update_layout(
                title="Resultados por dia (leads + conversas)",
                height=340, bargap=0.3, showlegend=False,
                yaxis=dict(title="Resultados", showgrid=True),
                margin=dict(l=8, r=8, t=40, b=8),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            _placeholder("Série de resultados aparece aqui após o primeiro sync", 340)

    # Linha 4 — por plataforma + melhores anúncios (donut estilo V4)
    if tem_ads:
        col_plat, col_donut = st.columns([1, 1.15])

        with col_plat:
            st.markdown("##### Por plataforma")
            plat = (
                ads_per.assign(_result=ads_per["leads"] + ads_per["mensagens"])
                .groupby("plataforma")
                .agg(Investimento=("spend", "sum"),
                     Resultados=("_result", "sum"),
                     Cliques=("cliques_link", "sum"),
                     Impressoes=("impressoes", "sum"))
                .reset_index()
            )
            plat["CPR"] = plat.apply(
                lambda r: r["Investimento"] / r["Resultados"] if r["Resultados"] else None, axis=1)
            plat["CTR"] = plat.apply(
                lambda r: r["Cliques"] / r["Impressoes"] if r["Impressoes"] else None, axis=1)
            plat = plat.sort_values("Investimento", ascending=False)[
                ["plataforma", "Investimento", "Resultados", "CPR", "CTR"]
            ].rename(columns={"plataforma": "Plataforma"})
            st.dataframe(
                plat, width="stretch", hide_index=True,
                column_config={
                    "Investimento": st.column_config.NumberColumn("Investimento", format="R$ %.0f"),
                    "Resultados": st.column_config.NumberColumn("Resultados", format="%d"),
                    "CPR": st.column_config.NumberColumn("CPR", format="R$ %.2f"),
                    "CTR": st.column_config.NumberColumn("CTR", format="percent"),
                },
            )
            st.caption("Meta e Google atualizam sozinhos, de hora em hora (sync automático na nuvem) — "
                       "Meta via Graph API/n8n, Google via Google Ads Script.")

        with col_donut:
            st.markdown("##### Melhores anúncios (por resultado)")
            _top_anuncios(ads_per)

    # Linha 5 — campanhas
    if tem_ads:
        st.markdown("##### Campanhas — investimento e resultados")
        camp = (
            ads_per.groupby("campanha")
            .agg(Investimento=("spend", "sum"),
                 Resultados=("leads", "sum"),
                 Mensagens=("mensagens", "sum"),
                 Cliques=("cliques_link", "sum"))
            .reset_index()
        )
        camp["Resultados"] = camp["Resultados"] + camp["Mensagens"]
        camp["CPR"] = camp.apply(
            lambda r: r["Investimento"] / r["Resultados"] if r["Resultados"] else None, axis=1
        )
        camp = camp.sort_values("Investimento", ascending=False)
        camp = camp.rename(columns={"campanha": "Campanha"})[
            ["Campanha", "Investimento", "Resultados", "CPR", "Cliques"]
        ]
        max_inv = float(camp["Investimento"].max()) if not camp.empty else 1.0
        st.dataframe(
            camp, width="stretch", hide_index=True,
            column_config={
                "Investimento": st.column_config.ProgressColumn(
                    "Investimento", format="R$ %.0f", min_value=0, max_value=max_inv),
                "Resultados": st.column_config.NumberColumn("Resultados", format="%d"),
                "CPR": st.column_config.NumberColumn("CPR", format="R$ %.2f"),
                "Cliques": st.column_config.NumberColumn("Cliques", format="%d"),
            },
        )
        if ads_per["fonte"].eq("demo").any():
            st.caption("🧪 Dados de demonstração (DEMO_ADS=1) — apenas para visualizar o layout. "
                       "Com o sync real do Meta, estes números vêm das campanhas de verdade.")


def _top_anuncios(ads_per: pd.DataFrame, topn: int = 7):
    """Ranking dos melhores anúncios por resultado — nome acima da barra, cor por plataforma."""
    tmp = ads_per.assign(_result=ads_per["leads"] + ads_per["mensagens"])
    tmp = tmp[tmp["anuncio"].fillna("").str.strip() != ""]
    if tmp.empty or tmp["_result"].sum() == 0:
        _placeholder("Aparece quando o sync trouxer anúncios com resultados", 320)
        return

    agg = (
        tmp.groupby("anuncio")
        .agg(resultado=("_result", "sum"),
             investimento=("spend", "sum"),
             plataforma=("plataforma", lambda s: s.value_counts().idxmax()))
        .sort_values("resultado", ascending=False)
        .head(topn)
        .iloc[::-1]  # maior resultado no topo (eixo y do Plotly cresce pra cima)
    )

    def _short(nome: str, n: int = 46) -> str:
        nome = str(nome).strip()
        return nome if len(nome) <= n else nome[: n - 1] + "…"

    nomes = agg.index.tolist()
    cores = [tema.CORES_CANAIS.get(p, tema.INK_MUTE) for p in agg["plataforma"]]
    cpr = [(inv / res) if res else 0 for inv, res in zip(agg["investimento"], agg["resultado"])]
    custom = list(zip(nomes, agg["plataforma"].tolist(), cpr))
    ypos = list(range(len(agg)))

    fig = go.Figure(
        go.Bar(
            y=ypos,
            x=agg["resultado"].tolist(),
            orientation="h",
            marker=dict(color=cores, cornerradius=5),
            text=[str(int(v)) for v in agg["resultado"]],
            textposition="outside",
            textfont=dict(size=12, color=tema.INK),
            cliponaxis=False,
            customdata=custom,
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                          "%{x} resultados · CPR R$ %{customdata[2]:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=48 * len(agg) + 44,
        margin=dict(l=6, r=46, t=8, b=8),
        bargap=0.55,
        showlegend=False,
        xaxis=dict(title=None, showgrid=True, zeroline=False),
        yaxis=dict(showticklabels=False, showgrid=False, range=[-0.6, len(agg) - 0.4]),
        annotations=[dict(x=0, y=i, text=_short(n), xanchor="left", yanchor="bottom",
                          yshift=7, showarrow=False, font=dict(size=11, color=tema.INK))
                     for i, n in enumerate(nomes)],
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("🔵 Meta Ads · 🟡 Google Ads — barra = resultados (leads + mensagens) no período; "
               "passe o mouse para ver o CPR de cada anúncio.")


def _placeholder(texto, altura):
    st.markdown(
        f"<div style='height:{altura}px;display:flex;align-items:center;justify-content:center;"
        f"text-align:center;border:1px dashed #dfdfdf;border-radius:12px;color:#9a9a9a;padding:24px'>"
        f"{texto}</div>",
        unsafe_allow_html=True,
    )


# ── Seção 2: Captação no CRM (Jetimob) ───────────────────────────────

def _secao_captacao(ctx):
    ini, fim, canais = ctx["ini"], ctx["fim"], ctx["canais"]
    ini_ant, fim_ant = dados.janela_anterior(ini, fim)

    leads_per = dados.filtrar_canais(dados.filtrar_periodo(ctx["leads"], "dia", ini, fim), canais)
    leads_ant = dados.filtrar_canais(dados.filtrar_periodo(ctx["leads"], "dia", ini_ant, fim_ant), canais)

    ads_per = _ads_do_periodo(ctx["ads"], ini, fim, canais)
    spend = float(ads_per["spend"].sum()) if ads_per is not None and not ads_per.empty else None
    leads_plataforma = int(ads_per["leads"].sum()) if ads_per is not None and not ads_per.empty else None

    st.markdown("#### Captação — leads no CRM (Jetimob)")
    total_leads = len(leads_per)
    total_ant = len(leads_ant)
    dias = max((fim - ini).days + 1, 1)
    cpl = (spend / leads_plataforma) if spend and leads_plataforma else None
    leads_pagos = len(leads_per[leads_per["canal"].isin(["Meta Ads", "Google Ads"])])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Leads", num(total_leads), delta=delta_pct(total_leads, total_ant),
              help=f"Comparado com {ini_ant.strftime('%d/%m')}–{fim_ant.strftime('%d/%m')}")
    k2.metric("Leads/dia", f"{total_leads / dias:.1f}".replace(".", ","))
    k3.metric("CPL mídia", brl(cpl, 2) if cpl else "—",
              help="Investimento ÷ leads reportados pelas plataformas de anúncio")
    k4.metric("Leads pagos", num(leads_pagos),
              help="Leads do Jetimob com origem Meta/Google. Muito abaixo dos leads da plataforma = "
                   "integração Facebook↔Jetimob precisa de atenção.")
    canal_top = leads_per["canal"].mode().iat[0] if total_leads else "—"
    k5.metric("Canal líder", canal_top, help="Canal com mais leads no período")

    col_a, col_b = st.columns(2)
    with col_a:
        serie = _serie_diaria(leads_per, "dia", ini, fim)
        fig = go.Figure(
            go.Scatter(
                x=list(serie.index), y=serie.values, mode="lines",
                line=dict(color=tema.COR_SERIE, width=2, shape="spline"),
                fill="tozeroy", fillcolor=tema.hex_rgba(tema.COR_SERIE, 0.08),
                hovertemplate="%{x|%d/%m/%Y}<br><b>%{y} leads</b><extra></extra>",
            )
        )
        fig.update_layout(title="Leads por dia", height=300, showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_b:
        por_canal = (
            leads_per.groupby("canal").size().reindex(tema.ORDEM_CANAIS).dropna().astype(int)
            if not leads_per.empty else pd.Series(dtype=int)
        )
        fig = go.Figure(
            go.Bar(
                y=por_canal.index.tolist()[::-1], x=por_canal.values.tolist()[::-1],
                orientation="h",
                marker=dict(color=[tema.CORES_CANAIS[c] for c in por_canal.index.tolist()[::-1]],
                            cornerradius=4),
                text=por_canal.values.tolist()[::-1], textposition="outside", cliponaxis=False,
                hovertemplate="%{y}: <b>%{x} leads</b><extra></extra>",
            )
        )
        fig.update_layout(title="Leads por canal", height=300, showlegend=False,
                          xaxis=dict(showgrid=True), yaxis=dict(showgrid=False),
                          margin=dict(l=8, r=56, t=36, b=8))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # Origens detalhadas + bairros
    col_c, col_d = st.columns(2)
    with col_c:
        st.markdown("##### Top origens (detalhe)")
        if leads_per.empty:
            st.caption("Sem leads no período.")
        else:
            origens = leads_per.groupby("origem").size().sort_values(ascending=False).head(10)
            fig = go.Figure(
                go.Bar(
                    y=origens.index.tolist()[::-1], x=origens.values.tolist()[::-1],
                    orientation="h", marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=origens.values.tolist()[::-1], textposition="outside", cliponaxis=False,
                    hovertemplate="%{y}: <b>%{x} leads</b><extra></extra>",
                )
            )
            fig.update_layout(height=320, showlegend=False, yaxis=dict(showgrid=False),
                              margin=dict(l=8, r=56, t=8, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_d:
        st.markdown("##### Bairros mais procurados")
        if leads_per.empty or leads_per["bairro"].dropna().empty:
            st.caption(
                "Sem informação de bairro nos leads do período — o webhook Jetimob→n8n ainda não "
                "grava bairro/código do imóvel (leads antigos importados têm). Dá pra enriquecer o "
                "workflow `capi_meta_jetimob_lead` no n8n."
            )
        else:
            bairros = (
                leads_per.dropna(subset=["bairro"]).groupby("bairro").size()
                .sort_values(ascending=False).head(10)
                .rename("Leads").reset_index().rename(columns={"bairro": "Bairro"})
            )
            st.dataframe(bairros, width="stretch", hide_index=True, height=320)


def render(ctx: dict) -> None:
    _secao_midia(ctx)
    st.divider()
    _secao_captacao(ctx)
