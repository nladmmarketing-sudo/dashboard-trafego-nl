"""Modelo 2 — Funil do Tráfego às Vendas (conexão tráfego + comercial).

Fluxo do período (leads → vendas, CAC, ROAS, custo por VGV) e fotografia
atual do kanban do Jetimob por etapa.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, brl_compacto, nome_abreviado, num, pct

ROTULO_CONTRATO = {"venda": "Venda", "locacao": "Locação", "temporada": "Temporada"}


def render(ctx: dict) -> None:
    ini, fim, canais = ctx["ini"], ctx["fim"], ctx["canais"]

    leads_per = dados.filtrar_canais(dados.filtrar_periodo(ctx["leads"], "dia", ini, fim), canais)
    vendas_per = dados.filtrar_canais(dados.filtrar_periodo(ctx["vendas"], "data_venda", ini, fim), canais)

    ads = ctx["ads"]
    spend = None
    if ads is not None and not ads.empty:
        ads_per = dados.filtrar_periodo(ads, "dia", ini, fim)
        spend = float(ads_per["spend"].sum()) if not ads_per.empty else 0.0

    vendas_venda = vendas_per[vendas_per["tipo_negocio"] == "Venda"]
    vgv = float(vendas_venda["valor"].fillna(0).sum())
    qtd_vendas = len(vendas_venda)
    qtd_locacoes = len(vendas_per[vendas_per["tipo_negocio"] == "Locação"])
    total_fechamentos = len(vendas_per)

    # ── Eficiência do período ────────────────────────────────────────
    st.markdown("#### Do lead ao fechamento — período selecionado")

    taxa_conv = (total_fechamentos / len(leads_per)) if len(leads_per) else None
    cac = (spend / total_fechamentos) if spend and total_fechamentos else None
    roas = (vgv / spend) if spend and vgv else None
    custo_vgv = (spend / vgv) if spend and vgv else None

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Leads", num(len(leads_per)))
    c2.metric("Fechamentos", num(total_fechamentos),
              help=f"{qtd_vendas} vendas + {qtd_locacoes} locações")
    c3.metric("Conversão lead→fechamento", pct(taxa_conv, 2) if taxa_conv is not None else "—",
              help="Fechamentos do período ÷ leads do período. Atenção: com ciclo de venda "
                   "longo, parte das vendas veio de leads de meses anteriores.")
    c4.metric("CAC (mídia)", brl(cac, 0) if cac else "—",
              help="Investimento em mídia ÷ fechamentos do período")
    c5.metric("ROAS (VGV)", f"{roas:.1f}×".replace(".", ",") if roas else "—",
              help="VGV de vendas ÷ investimento em mídia")
    c6.metric("Custo por VGV", pct(custo_vgv, 2) if custo_vgv else "—",
              help="Quanto de mídia foi gasto para cada R$ 1 de VGV")

    if spend is None:
        st.caption("💡 CAC, ROAS e Custo por VGV aparecem quando houver investimento registrado "
                   "(sync do Meta ou lançamento manual na aba Executivo).")

    st.divider()

    col_funil, col_kanban = st.columns([1, 1])

    # ── Funil do período (fluxo) ─────────────────────────────────────
    with col_funil:
        etapas = ["Leads captados", "Fechamentos"]
        valores = [len(leads_per), total_fechamentos]
        fig = go.Figure(
            go.Funnel(
                y=etapas,
                x=valores,
                marker=dict(color=[tema.RAMPA_AZUL[2], tema.RAMPA_AZUL[5]]),
                textinfo="value+percent initial",
                textfont=dict(size=14),
                connector=dict(line=dict(color=tema.HAIRLINE, width=1)),
                hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
            )
        )
        fig.update_layout(title=f"Fluxo do período ({ini.strftime('%d/%m')}–{fim.strftime('%d/%m')})",
                          height=340, showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Fluxo real do período: leads que entraram × negócios fechados. "
                   "As etapas intermediárias vivem no kanban ao lado.")

    # ── Fotografia do kanban (estoque atual) ─────────────────────────
    with col_kanban:
        funil = ctx["funil"]
        if funil is None:
            st.markdown(
                "<div style='height:340px;border:1px dashed #dfdfdf;border-radius:12px;"
                "color:#9a9a9a;padding:24px;display:flex;flex-direction:column;"
                "align-items:center;justify-content:center;text-align:center;gap:8px'>"
                "<span>Fotografia do kanban aparece aqui após rodar</span>"
                "<code>sync/sync_funil_jetimob.py</code>"
                "<span>(etapas: atendimento → agendamento → visita → proposta)</span></div>",
                unsafe_allow_html=True,
            )
        else:
            df_funil, snapshot_em = funil
            contratos = sorted(df_funil["contrato"].unique().tolist())
            rotulos = [ROTULO_CONTRATO.get(c, c.title()) for c in contratos]
            escolhido = st.radio("Kanban", rotulos, horizontal=True, label_visibility="collapsed")
            contrato = contratos[rotulos.index(escolhido)]
            sub = df_funil[df_funil["contrato"] == contrato].sort_values("posicao_etapa")
            n = max(len(sub), 1)
            cores = [tema.RAMPA_AZUL[min(int(i * (len(tema.RAMPA_AZUL) - 1) / max(n - 1, 1)), len(tema.RAMPA_AZUL) - 1)]
                     for i in range(n)]
            fig = go.Figure(
                go.Funnel(
                    y=sub["etapa"].tolist(),
                    x=sub["qtd"].tolist(),
                    marker=dict(color=cores),
                    textinfo="value",
                    connector=dict(line=dict(color=tema.HAIRLINE, width=1)),
                    hovertemplate="%{y}: <b>%{x} oportunidades</b><extra></extra>",
                )
            )
            fig.update_layout(title=f"Kanban agora — {escolhido}", height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption(f"Fotografia de {snapshot_em.strftime('%d/%m/%Y %H:%M')} — estoque de "
                       "oportunidades abertas por etapa (não é fluxo do período).")

    st.divider()

    # ── Conversão por canal ──────────────────────────────────────────
    st.markdown("#### Conversão por canal")
    if leads_per.empty:
        st.caption("Sem leads no período.")
    else:
        lead_canal = leads_per.groupby("canal").size().rename("Leads")
        venda_canal = vendas_per.groupby("canal").size().rename("Fechamentos")
        vgv_canal = vendas_venda.groupby("canal")["valor"].sum().rename("VGV (R$)")
        tab = (
            pd.concat([lead_canal, venda_canal, vgv_canal], axis=1)
            .reindex(tema.ORDEM_CANAIS).dropna(how="all").fillna(0)
        )
        tab["Leads"] = tab["Leads"].astype(int)
        tab["Fechamentos"] = tab["Fechamentos"].astype(int)
        tab["Conversão"] = tab.apply(
            lambda r: pct(r["Fechamentos"] / r["Leads"], 2) if r["Leads"] else "—", axis=1
        )
        tab["VGV (R$)"] = tab["VGV (R$)"].map(lambda v: brl(v) if v else "—")
        st.dataframe(tab.reset_index().rename(columns={"canal": "Canal"}),
                     width="stretch", hide_index=True)
        st.caption("⚠️ 27 de 41 vendas históricas estão sem origem preenchida no Jetimob — "
                   "cobrar preenchimento da origem no fechamento melhora esta análise.")

    # ── Fechamentos do período + ranking de corretores ───────────────
    col_v, col_r = st.columns([3, 2])

    with col_v:
        st.markdown("#### Fechamentos no período")
        if vendas_per.empty:
            st.caption("Nenhum fechamento no período selecionado.")
        else:
            tab_v = vendas_per.sort_values("data_venda", ascending=False).copy()
            tab_v["Data"] = tab_v["data_venda"].map(lambda d: d.strftime("%d/%m/%Y"))
            tab_v["Cliente"] = tab_v["nome_cliente"].map(nome_abreviado)
            tab_v["Código"] = tab_v.get("codigo_imovel", "").map(
                lambda c: str(c).strip() if pd.notna(c) and str(c).strip() else "—")
            tab_v["Valor"] = tab_v["valor"].map(lambda v: brl(v) if pd.notna(v) else "—")
            tab_v = tab_v[["Data", "Cliente", "Código", "tipo_negocio", "Valor", "corretor", "origem_lead"]]
            tab_v.columns = ["Data", "Cliente", "Código", "Tipo", "Valor", "Corretor", "Origem"]
            st.dataframe(tab_v, width="stretch", hide_index=True, height=320)

    with col_r:
        st.markdown("#### Ranking de corretores")
        if vendas_per.empty:
            st.caption("—")
        else:
            rank = (
                vendas_per.groupby("corretor")
                .agg(Fechamentos=("corretor", "size"), VGV=("valor", "sum"))
                .sort_values(["Fechamentos", "VGV"], ascending=False).head(8)
            )
            fig = go.Figure(
                go.Bar(
                    y=rank.index.tolist()[::-1],
                    x=rank["Fechamentos"].tolist()[::-1],
                    orientation="h",
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=[f"{f}  ·  {brl_compacto(v)}" for f, v in
                          zip(rank["Fechamentos"].tolist()[::-1], rank["VGV"].tolist()[::-1])],
                    textposition="outside",
                cliponaxis=False,
                    hovertemplate="%{y}: <b>%{x} fechamentos</b><extra></extra>",
                )
            )
            fig.update_layout(height=320, showlegend=False,
                              xaxis=dict(showgrid=True), yaxis=dict(showgrid=False),
                              margin=dict(l=8, r=80, t=8, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
