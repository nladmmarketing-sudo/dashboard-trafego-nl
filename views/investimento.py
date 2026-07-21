"""Aba Investimento em Marketing — CAC real da empresa.

Soma a mídia paga (Meta/Google, automática) com os custos fixos
(plataforma/CRM, portais, ferramentas) para calcular o custo total de
marketing e, a partir dele, o CAC real, o custo por lead e o custo por VGV.
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, brl_compacto, delta_pct, num, pct
from utils.supabase import atualizar, deletar, inserir

COR_MIDIA = tema.COR_INVESTIMENTO          # azul
CORES_CAT = {
    "Mídia paga": COR_MIDIA,
    "Plataforma/CRM": "#008300",           # verde
    "Portais": "#4a3aa7",                  # violeta
    "Ferramentas/Apps": "#eda100",         # âmbar
}
ORDEM_CAT = ["Mídia paga", "Plataforma/CRM", "Portais", "Ferramentas/Apps"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _fim_mes(m: date) -> date:
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _rotulo(m: date) -> str:
    return f"{MESES[m.month - 1]}/{str(m.year)[2:]}"


def _media_do_mes(ads, m: date) -> float:
    if ads is None or ads.empty:
        return 0.0
    sub = ads[(ads["dia"] >= m.replace(day=1)) & (ads["dia"] <= _fim_mes(m))]
    return float(sub["spend"].sum())


def _fixos_por_categoria(custos, m: date) -> dict:
    """{categoria: soma valor_mensal} dos custos ativos no mês."""
    aplic = dados.custos_do_mes(custos, m) if custos is not None else None
    if aplic is None or aplic.empty:
        return {}
    return aplic.groupby("categoria")["valor_mensal"].sum().to_dict()


def render(ctx: dict) -> None:
    custos = ctx.get("custos")
    ads, vendas, leads = ctx["ads"], ctx["vendas"], ctx["leads"]

    if custos is None:
        st.warning(
            "**Tabela de custos ainda não existe.** Rode `sql/02_custos_marketing.sql` no "
            "SQL Editor do Supabase para habilitar o cadastro de plataformas/apps. "
            "Enquanto isso, a mídia paga já aparece abaixo.",
            icon="🔌",
        )

    hoje = dados.hoje_local()
    meses = sorted(
        {d.replace(day=1) for d in leads["dia"]} if not leads.empty else {hoje.replace(day=1)},
        reverse=True,
    )[:12] or [hoje.replace(day=1)]
    rotulos = [_rotulo(m) for m in meses]
    escolhido = st.selectbox("Mês de referência", rotulos, index=0, key="mes_investimento")
    mes = meses[rotulos.index(escolhido)]
    mes_ant = (mes.replace(day=1) - timedelta(days=1)).replace(day=1)

    # ── Totais do mês e do anterior ──────────────────────────────────
    def totais(m):
        media = _media_do_mes(ads, m)
        fixos = _fixos_por_categoria(custos, m)
        total_fixos = sum(fixos.values())
        return media, fixos, total_fixos, media + total_fixos

    media, fixos, total_fixos, total = totais(mes)
    media_a, _, total_fixos_a, total_a = totais(mes_ant)

    # Resultados do mês (para CAC/ROI)
    def no_mes(df, col):
        if df is None or df.empty:
            return df
        return df[(df[col] >= mes.replace(day=1)) & (df[col] <= _fim_mes(mes))]

    leads_m = no_mes(leads, "dia")
    vendas_m = no_mes(vendas, "data_venda")
    n_leads = len(leads_m) if leads_m is not None else 0
    fechamentos = len(vendas_m) if vendas_m is not None else 0
    vendas_venda = vendas_m[vendas_m["tipo_negocio"] == "Venda"] if vendas_m is not None and not vendas_m.empty else pd.DataFrame()
    vgv = float(vendas_venda["valor"].fillna(0).sum()) if not vendas_venda.empty else 0.0

    # ── KPIs ─────────────────────────────────────────────────────────
    st.markdown(f"#### Investimento total de marketing — {escolhido}")
    if mes == hoje.replace(day=1):
        st.caption("⏳ Mês em andamento — mídia parcial; custos fixos são do mês cheio.")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Investimento total", brl(total, 0), delta=delta_pct(total, total_a),
              delta_color="inverse", help="Mídia paga + custos fixos (plataformas/apps)")
    c2.metric("Mídia paga", brl(media, 0), help="Meta + Google no mês (automático)")
    c3.metric("Custos fixos", brl(total_fixos, 0), help="Plataforma/CRM + portais + ferramentas")
    cac = (total / fechamentos) if fechamentos else None
    c4.metric("CAC real", brl(cac, 0) if cac else "—",
              help=f"Investimento total ÷ {fechamentos} fechamentos (vendas + locações)")
    cpl = (total / n_leads) if n_leads else None
    c5.metric("Custo por lead", brl(cpl, 2) if cpl else "—",
              help="Investimento total ÷ leads do mês")
    custo_vgv = (total / vgv) if vgv else None
    c6.metric("Custo por VGV", pct(custo_vgv, 2) if custo_vgv else "—",
              help="Quanto de marketing para cada R$ 1 de VGV vendido")

    pct_midia = (media / total) if total else 0
    st.caption(f"Composição: **{pct(pct_midia, 0)}** mídia · **{pct(1 - pct_midia, 0)}** ferramentas/plataformas. "
               f"O CAC do painel de vendas usa só mídia; aqui é o **CAC real da empresa** (com tudo).")

    st.divider()

    # ── Rateio por categoria + evolução mensal ───────────────────────
    col_r, col_e = st.columns([1, 1.3])

    with col_r:
        st.markdown("###### Rateio do mês por categoria")
        rateio = {"Mídia paga": media, **{c: fixos.get(c, 0) for c in ORDEM_CAT[1:]}}
        rateio = {k: v for k, v in rateio.items() if v > 0}
        if not rateio:
            _placeholder("Sem custos no mês", 280)
        else:
            itens = sorted(rateio.items(), key=lambda kv: kv[1])
            fig = go.Figure(
                go.Bar(
                    y=[k for k, _ in itens], x=[v for _, v in itens], orientation="h",
                    marker=dict(color=[CORES_CAT[k] for k, _ in itens], cornerradius=4),
                    text=[brl(v, 0) for _, v in itens], textposition="outside", cliponaxis=False,
                    hovertemplate="%{y}: <b>R$ %{x:,.0f}</b><extra></extra>",
                )
            )
            fig.update_layout(height=280, showlegend=False,
                              yaxis=dict(showgrid=False), margin=dict(l=8, r=70, t=8, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_e:
        st.markdown("###### Evolução do investimento (empilhado)")
        ult = sorted(meses)[-8:]
        fig = go.Figure()
        for cat in ORDEM_CAT:
            if cat == "Mídia paga":
                vals = [_media_do_mes(ads, m) for m in ult]
            else:
                vals = [_fixos_por_categoria(custos, m).get(cat, 0) for m in ult]
            if sum(vals) == 0:
                continue
            fig.add_bar(x=[_rotulo(m) for m in ult], y=vals, name=cat,
                        marker=dict(color=CORES_CAT[cat]),
                        hovertemplate="%{x} · " + cat + ": <b>R$ %{y:,.0f}</b><extra></extra>")
        fig.update_layout(barmode="stack", height=280,
                          legend=dict(orientation="h", y=1.04, x=0, font=dict(size=11)),
                          margin=dict(l=8, r=8, t=28, b=8))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ── Cadastro / edição de custos fixos ────────────────────────────
    st.divider()
    st.markdown("#### Custos fixos cadastrados")
    if custos is None:
        st.caption("Cadastro disponível após criar a tabela `custos_marketing`.")
        return

    _editor_custos(custos)


def _editor_custos(custos: pd.DataFrame):
    ativos = custos[custos["ativo"]] if not custos.empty else custos
    if ativos is not None and not ativos.empty:
        tab = ativos.copy()
        tab["Valor/mês"] = tab["valor_mensal"].map(lambda v: brl(v, 2))
        tab["Desde"] = tab["mes_inicio"].map(lambda d: d.strftime("%m/%Y") if d else "—")
        tab = tab[["categoria", "item", "Valor/mês", "Desde"]].rename(
            columns={"categoria": "Categoria", "item": "Item"})
        total = float(ativos["valor_mensal"].sum())
        st.dataframe(tab, width="stretch", hide_index=True)
        st.caption(f"**Total fixo recorrente: {brl(total, 2)}/mês** (mídia paga entra à parte, automática).")
    else:
        st.caption("Nenhum custo cadastrado ainda. Adicione abaixo 👇")

    with st.expander("➕ Adicionar custo"):
        with st.form("add_custo"):
            f1, f2, f3 = st.columns([1.2, 1.5, 1])
            categoria = f1.selectbox("Categoria", dados.CATEGORIAS_CUSTO)
            item = f2.text_input("Item", placeholder="ex.: Jetimob, ZAP Imóveis, n8n")
            valor = f3.number_input("Valor mensal (R$)", min_value=0.0, step=50.0, format="%.2f")
            g1, g2 = st.columns(2)
            desde = g1.date_input("Desde (mês)", value=dados.hoje_local().replace(day=1))
            obs = g2.text_input("Observação (opcional)")
            ok = st.form_submit_button("Salvar custo", type="primary")
        if ok and item.strip() and valor > 0:
            try:
                inserir("custos_marketing", [{
                    "categoria": categoria, "item": item.strip(),
                    "valor_mensal": valor, "mes_inicio": desde.replace(day=1).isoformat(),
                    "ativo": True, "obs": obs or None,
                }], on_conflict="categoria,item,mes_inicio")
                st.cache_data.clear()
                st.success(f"{item} adicionado ({brl(valor, 2)}/mês).")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    if ativos is not None and not ativos.empty:
        with st.expander("✏️ Editar valor / encerrar custo"):
            opcoes = {f"{r['categoria']} · {r['item']} ({brl(r['valor_mensal'], 2)})": r["id"]
                      for _, r in ativos.iterrows()}
            escolha = st.selectbox("Custo", list(opcoes.keys()))
            cid = opcoes[escolha]
            e1, e2 = st.columns(2)
            novo_valor = e1.number_input("Novo valor mensal (R$)", min_value=0.0, step=50.0, format="%.2f")
            with e2:
                st.write("")
                st.write("")
                col_a, col_b = st.columns(2)
                salvar = col_a.button("💾 Atualizar valor", use_container_width=True)
                encerrar = col_b.button("🚫 Encerrar", use_container_width=True,
                                        help="Marca como inativo — para de contar nos próximos meses")
            if salvar and novo_valor > 0:
                atualizar("custos_marketing", cid,
                          {"valor_mensal": novo_valor, "atualizado_em": "now()"})
                st.cache_data.clear()
                st.success("Valor atualizado.")
                st.rerun()
            if encerrar:
                atualizar("custos_marketing", cid,
                          {"ativo": False, "mes_fim": dados.hoje_local().replace(day=1).isoformat()})
                st.cache_data.clear()
                st.success("Custo encerrado.")
                st.rerun()


def _placeholder(texto, altura):
    st.markdown(
        f"<div style='height:{altura}px;display:flex;align-items:center;justify-content:center;"
        f"text-align:center;border:1px dashed #dfdfdf;border-radius:12px;color:#9a9a9a'>{texto}</div>",
        unsafe_allow_html=True,
    )
