"""Modelo 1 — Visão Geral de Performance (o dia a dia do gestor).

Topo do funil (investimento, alcance, CPC/CTR), captação (leads, CPL)
e distribuição por canal / origem / bairro.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, brl_compacto, delta_pct, num, pct


def _ads_do_periodo(ads: pd.DataFrame | None, ini, fim, canais: list[str]) -> pd.DataFrame | None:
    if ads is None:
        return None
    plataformas = [c for c in canais if c in ("Meta Ads", "Google Ads")]
    df = dados.filtrar_periodo(ads, "dia", ini, fim)
    if df is None or df.empty:
        return df
    return df[df["plataforma"].isin(plataformas)] if plataformas else df.iloc[0:0]


def _aviso_investimento(ads: pd.DataFrame | None) -> None:
    if ads is None:
        st.info(
            "**Investimento ainda não conectado.** Rode o arquivo `sql/01_trafego_pago_schema.sql` "
            "no SQL Editor do Supabase e depois execute `sync/sync_meta_ads.py` (ou lance o valor "
            "manualmente na aba Executivo). O restante do painel já funciona normalmente.",
            icon="🔌",
        )
    elif ads.empty:
        st.info(
            "**Sem dados de investimento no período.** Execute `sync/sync_meta_ads.py` com um token "
            "válido do Meta (ver README) ou lance o investimento manualmente na aba Executivo.",
            icon="💸",
        )


def _serie_diaria(df: pd.DataFrame, col_dia: str, ini, fim, col_valor: str | None = None) -> pd.DataFrame:
    """Agrega por dia e preenche dias sem registro com zero."""
    idx = pd.date_range(ini, fim, freq="D").date
    if df is None or df.empty:
        return pd.DataFrame({"dia": idx, "valor": [0] * len(idx)})
    if col_valor:
        s = df.groupby(col_dia)[col_valor].sum()
    else:
        s = df.groupby(col_dia).size()
    s = s.reindex(idx, fill_value=0)
    return pd.DataFrame({"dia": idx, "valor": s.values})


def render(ctx: dict) -> None:
    ini, fim, canais = ctx["ini"], ctx["fim"], ctx["canais"]

    leads_todos = ctx["leads"]
    leads_per = dados.filtrar_canais(dados.filtrar_periodo(leads_todos, "dia", ini, fim), canais)
    ini_ant, fim_ant = dados.janela_anterior(ini, fim)
    leads_ant = dados.filtrar_canais(dados.filtrar_periodo(leads_todos, "dia", ini_ant, fim_ant), canais)

    ads_per = _ads_do_periodo(ctx["ads"], ini, fim, canais)
    ads_ant = _ads_do_periodo(ctx["ads"], ini_ant, fim_ant, canais)

    # ── KPIs financeiros (topo do funil) ─────────────────────────────
    st.markdown("#### Mídia paga — topo do funil")
    _aviso_investimento(ctx["ads"] if ads_per is None or ads_per.empty else ads_per)

    tem_ads = ads_per is not None and not ads_per.empty
    spend = float(ads_per["spend"].sum()) if tem_ads else None
    impress = int(ads_per["impressoes"].sum()) if tem_ads else None
    cliques = int(ads_per["cliques_link"].sum() or ads_per["cliques"].sum()) if tem_ads else None
    leads_plataforma = int(ads_per["leads"].sum()) if tem_ads else None

    spend_ant = float(ads_ant["spend"].sum()) if ads_ant is not None and not ads_ant.empty else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Investimento", brl(spend, 2) if spend is not None else "—",
              delta=delta_pct(spend, spend_ant), help="Soma do gasto Meta + Google no período")
    c2.metric("Impressões", num(impress) if impress is not None else "—")
    c3.metric("Cliques (link)", num(cliques) if cliques is not None else "—")
    ctr = (cliques / impress) if impress else None
    c4.metric("CTR", pct(ctr, 2) if ctr is not None else "—",
              help="Cliques no link ÷ impressões")
    cpc = (spend / cliques) if cliques else None
    c5.metric("CPC médio", brl(cpc, 2) if cpc is not None else "—")

    # ── KPIs de captação ─────────────────────────────────────────────
    st.markdown("#### Captação — leads no CRM (Jetimob)")
    total_leads = len(leads_per)
    total_ant = len(leads_ant)
    dias = max((fim - ini).days + 1, 1)

    cpl_plataforma = (spend / leads_plataforma) if spend and leads_plataforma else None
    leads_pagos_crm = len(leads_per[leads_per["canal"].isin(["Meta Ads", "Google Ads"])])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Leads", num(total_leads), delta=delta_pct(total_leads, total_ant),
              help=f"Leads no período. Comparado com {ini_ant.strftime('%d/%m')}–{fim_ant.strftime('%d/%m')}")
    k2.metric("Leads/dia", f"{total_leads / dias:.1f}".replace(".", ","))
    k3.metric("CPL mídia", brl(cpl_plataforma, 2) if cpl_plataforma else "—",
              help="Investimento ÷ leads reportados pelas plataformas de anúncio")
    k4.metric("Leads pagos", num(leads_pagos_crm),
              help="Leads do Jetimob com origem Meta/Google — se estiver muito abaixo dos leads "
                   "da plataforma, a integração Facebook↔Jetimob precisa de atenção")
    canal_top = leads_per["canal"].mode().iat[0] if total_leads else "—"
    k5.metric("Canal líder", canal_top,
              help="Canal com mais leads no período")

    st.divider()

    # ── Séries diárias ───────────────────────────────────────────────
    col_esq, col_dir = st.columns(2)

    with col_esq:
        serie_leads = _serie_diaria(leads_per, "dia", ini, fim)
        fig = go.Figure(
            go.Scatter(
                x=serie_leads["dia"], y=serie_leads["valor"],
                mode="lines+markers",
                line=dict(color=tema.COR_SERIE, width=2),
                marker=dict(size=5),
                fill="tozeroy",
                fillcolor="rgba(42,120,214,0.08)",
                hovertemplate="%{x|%d/%m/%Y}<br><b>%{y} leads</b><extra></extra>",
                name="Leads",
            )
        )
        fig.update_layout(title="Leads por dia", height=300, showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_dir:
        if tem_ads:
            serie_spend = _serie_diaria(ads_per, "dia", ini, fim, "spend")
            fig = go.Figure(
                go.Bar(
                    x=serie_spend["dia"], y=serie_spend["valor"],
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    hovertemplate="%{x|%d/%m/%Y}<br><b>R$ %{y:,.2f}</b><extra></extra>",
                    name="Investimento",
                )
            )
            fig.update_layout(title="Investimento por dia (R$)", height=300, showlegend=False, bargap=0.35)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.markdown(
                "<div style='height:300px;display:flex;align-items:center;justify-content:center;"
                "border:1px dashed #dfdfdf;border-radius:12px;color:#9a9a9a'>"
                "Investimento por dia aparece aqui após o primeiro sync</div>",
                unsafe_allow_html=True,
            )

    # ── Distribuição por canal e origem ──────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        por_canal = (
            leads_per.groupby("canal").size().reindex(tema.ORDEM_CANAIS).dropna().astype(int)
            if not leads_per.empty else pd.Series(dtype=int)
        )
        fig = go.Figure(
            go.Bar(
                y=por_canal.index.tolist()[::-1],
                x=por_canal.values.tolist()[::-1],
                orientation="h",
                marker=dict(
                    color=[tema.CORES_CANAIS[c] for c in por_canal.index.tolist()[::-1]],
                    cornerradius=4,
                ),
                text=por_canal.values.tolist()[::-1],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}: <b>%{x} leads</b><extra></extra>",
            )
        )
        fig.update_layout(title="Leads por canal", height=320, showlegend=False,
                          xaxis=dict(showgrid=True), yaxis=dict(showgrid=False),
                          margin=dict(l=8, r=56, t=36, b=8))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_b:
        if tem_ads:
            por_plat = ads_per.groupby("plataforma")["spend"].sum()
            fig = go.Figure(
                go.Bar(
                    x=por_plat.index.tolist(),
                    y=por_plat.values.tolist(),
                    marker=dict(
                        color=[tema.CORES_PLATAFORMA.get(p, tema.COR_SERIE) for p in por_plat.index],
                        cornerradius=4,
                    ),
                    text=[brl_compacto(v) for v in por_plat.values],
                    textposition="outside",
                cliponaxis=False,
                    hovertemplate="%{x}: <b>R$ %{y:,.2f}</b><extra></extra>",
                )
            )
            fig.update_layout(title="Investimento por plataforma", height=320, showlegend=False, bargap=0.45)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            origens = leads_per.groupby("origem").size().sort_values(ascending=False).head(10)
            fig = go.Figure(
                go.Bar(
                    y=origens.index.tolist()[::-1],
                    x=origens.values.tolist()[::-1],
                    orientation="h",
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=origens.values.tolist()[::-1],
                    textposition="outside",
                cliponaxis=False,
                    hovertemplate="%{y}: <b>%{x} leads</b><extra></extra>",
                )
            )
            fig.update_layout(title="Top 10 origens (detalhe)", height=320, showlegend=False,
                              yaxis=dict(showgrid=False),
                              margin=dict(l=8, r=56, t=36, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ── Bairros mais procurados ──────────────────────────────────────
    st.markdown("#### Bairros mais procurados no período")
    if leads_per.empty or leads_per["bairro"].dropna().empty:
        st.caption(
            "Sem informação de bairro nos leads do período — o webhook Jetimob→n8n ainda não grava "
            "bairro/código do imóvel (leads antigos importados têm). Dá pra enriquecer o workflow "
            "`capi_meta_jetimob_lead` no n8n para preencher esses campos."
        )
    else:
        bairros = (
            leads_per.dropna(subset=["bairro"])
            .groupby("bairro").size().sort_values(ascending=False).head(10)
            .rename("Leads").reset_index().rename(columns={"bairro": "Bairro"})
        )
        st.dataframe(bairros, width="stretch", hide_index=True)

    # ── Tabela de apoio (regra de acessibilidade: sempre há visão tabular)
    with st.expander("📄 Ver dados em tabela"):
        st.markdown("**Leads por canal**")
        tab_canal = leads_per.groupby("canal").size().rename("Leads").reset_index() if not leads_per.empty else pd.DataFrame()
        st.dataframe(tab_canal, width="stretch", hide_index=True)
        if tem_ads:
            st.markdown("**Investimento por campanha**")
            tab_ads = (
                ads_per.groupby(["plataforma", "campanha"])
                .agg(spend=("spend", "sum"), impressoes=("impressoes", "sum"),
                     cliques_link=("cliques_link", "sum"), leads=("leads", "sum"))
                .reset_index().sort_values("spend", ascending=False)
            )
            st.dataframe(tab_ads, width="stretch", hide_index=True)
