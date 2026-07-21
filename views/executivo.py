"""Modelo 3 — Visão Executiva / Diretoria.

Mês vs mês anterior, VGV oficial, custo por VGV, rankings de procura
e aproveitamento por corretor. Inclui lançamento manual de investimento.
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, brl_compacto, delta_pct, num, pct
from utils.supabase import TabelaInexistente, inserir


def _mes_anterior(m: date) -> date:
    return (m.replace(day=1) - timedelta(days=1)).replace(day=1)


def _fim_do_mes(m: date) -> date:
    proximo = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return proximo - timedelta(days=1)


def _rotulo_mes(m: date) -> str:
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{meses[m.month - 1]}/{str(m.year)[2:]}"


def _vgv_mensal_consolidado(resumo: pd.DataFrame, vendas: pd.DataFrame) -> pd.DataFrame:
    """VGV de VENDAS por mês. Usa o relatório oficial do Jetimob quando o número
    é final (raspado após o fim do mês); caso contrário usa o kanban (vendas_nl)."""
    oficial = {}
    if not resumo.empty:
        r = resumo[resumo["tipo"] == "venda"].copy()
        r["scraped_at"] = pd.to_datetime(r["scraped_at"], utc=True, format="ISO8601")
        for _, row in r.iterrows():
            final = row["scraped_at"].date() > _fim_do_mes(row["mes"])
            if final:
                oficial[row["mes"]] = {"vgv": row["valor"], "qtd": row["qtd"], "fonte": "oficial"}

    kanban = {}
    if not vendas.empty:
        vv = vendas[vendas["tipo_negocio"] == "Venda"].copy()
        vv["mes"] = vv["data_venda"].map(lambda d: d.replace(day=1))
        g = vv.groupby("mes").agg(vgv=("valor", "sum"), qtd=("valor", "size"))
        for m, row in g.iterrows():
            kanban[m] = {"vgv": float(row["vgv"] or 0), "qtd": int(row["qtd"]), "fonte": "kanban"}

    meses = sorted(set(oficial) | set(kanban))
    linhas = [{"mes": m, **(oficial.get(m) or kanban.get(m))} for m in meses]
    return pd.DataFrame(linhas)


def render(ctx: dict) -> None:
    leads, vendas, resumo, ads = ctx["leads"], ctx["vendas"], ctx["resumo_mensal"], ctx["ads"]

    hoje = dados.hoje_local()
    meses_disponiveis = sorted(
        {d.replace(day=1) for d in leads["dia"]} | {v.replace(day=1) for v in vendas["data_venda"]}
        if not leads.empty or not vendas.empty else {hoje.replace(day=1)},
        reverse=True,
    )[:12]
    rotulos = [_rotulo_mes(m) for m in meses_disponiveis]
    escolhido = st.selectbox("Mês de referência", rotulos, index=0)
    mes = meses_disponiveis[rotulos.index(escolhido)]
    mes_ant = _mes_anterior(mes)

    def recorte_mes(df, col, m):
        if df is None or df.empty:
            return df
        return df[(df[col] >= m) & (df[col] <= _fim_do_mes(m))]

    leads_m, leads_a = recorte_mes(leads, "dia", mes), recorte_mes(leads, "dia", mes_ant)
    vendas_m, vendas_a = recorte_mes(vendas, "data_venda", mes), recorte_mes(vendas, "data_venda", mes_ant)
    ads_m = recorte_mes(ads, "dia", mes) if ads is not None else None
    ads_a = recorte_mes(ads, "dia", mes_ant) if ads is not None else None

    consolidado = _vgv_mensal_consolidado(resumo, vendas)

    def vgv_qtd(m):
        row = consolidado[consolidado["mes"] == m] if not consolidado.empty else pd.DataFrame()
        if row.empty:
            return 0.0, 0, "kanban"
        return float(row["vgv"].iat[0]), int(row["qtd"].iat[0]), row["fonte"].iat[0]

    vgv_m, qtd_m, fonte_m = vgv_qtd(mes)
    vgv_a, qtd_a, _ = vgv_qtd(mes_ant)

    loc_m = len(vendas_m[vendas_m["tipo_negocio"] == "Locação"]) if not vendas_m.empty else 0
    loc_a = len(vendas_a[vendas_a["tipo_negocio"] == "Locação"]) if not vendas_a.empty else 0

    spend_m = float(ads_m["spend"].sum()) if ads_m is not None and not ads_m.empty else None
    spend_a = float(ads_a["spend"].sum()) if ads_a is not None and not ads_a.empty else None
    leads_plat_m = int(ads_m["leads"].sum()) if ads_m is not None and not ads_m.empty else None

    # ── Big numbers ──────────────────────────────────────────────────
    st.markdown(f"#### {escolhido} × {_rotulo_mes(mes_ant)}")
    if mes == hoje.replace(day=1):
        st.caption(f"⏳ {escolhido} em andamento — números parciais até {hoje.strftime('%d/%m')}.")
    b1, b2, b3, b4, b5, b6 = st.columns(6)
    b1.metric("VGV vendas", brl_compacto(vgv_m), delta=delta_pct(vgv_m, vgv_a),
              help=f"Fonte: {'relatório oficial Jetimob' if fonte_m == 'oficial' else 'kanban Jetimob (parcial até bater o relatório oficial)'}")
    b2.metric("Vendas", num(qtd_m), delta=delta_pct(qtd_m, qtd_a))
    b3.metric("Locações", num(loc_m), delta=delta_pct(loc_m, loc_a))
    b4.metric("Leads", num(len(leads_m)), delta=delta_pct(len(leads_m), len(leads_a)))
    b5.metric("Investimento", brl(spend_m, 0) if spend_m is not None else "—",
              delta=delta_pct(spend_m, spend_a))
    cpl = (spend_m / leads_plat_m) if spend_m and leads_plat_m else None
    b6.metric("CPL mídia", brl(cpl, 2) if cpl else "—",
              help="Investimento ÷ leads reportados pelas plataformas de anúncio")

    custo_vgv = (spend_m / vgv_m) if spend_m and vgv_m else None
    if custo_vgv is not None:
        st.caption(f"**Custo por VGV:** {pct(custo_vgv, 2)} — cada R$ 1 de VGV custou "
                   f"{brl(custo_vgv * 100, 2)} a cada R$ 100 investidos em mídia.")

    st.divider()

    # ── Séries mensais ───────────────────────────────────────────────
    col_vgv, col_leads = st.columns(2)

    with col_vgv:
        if consolidado.empty:
            st.caption("Sem histórico de VGV.")
        else:
            ult = consolidado.sort_values("mes").tail(12)
            fig = go.Figure(
                go.Bar(
                    x=[_rotulo_mes(m) for m in ult["mes"]],
                    y=ult["vgv"],
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=[brl_compacto(v) for v in ult["vgv"]],
                    textposition="outside",
                cliponaxis=False,
                    textfont=dict(size=11),
                    customdata=[["Relatório oficial" if f == "oficial" else "Kanban (parcial)"] for f in ult["fonte"]],
                    hovertemplate="%{x}: <b>R$ %{y:,.0f}</b><br>%{customdata[0]}<extra></extra>",
                )
            )
            fig.update_layout(title="VGV de vendas por mês", height=320, showlegend=False, bargap=0.35)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_leads:
        if leads.empty:
            st.caption("Sem histórico de leads.")
        else:
            lm = leads.copy()
            lm["mes"] = lm["dia"].map(lambda d: d.replace(day=1))
            serie = lm.groupby("mes").size().sort_index().tail(12)
            fig = go.Figure(
                go.Bar(
                    x=[_rotulo_mes(m) for m in serie.index],
                    y=serie.values,
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=serie.values,
                    textposition="outside",
                cliponaxis=False,
                    textfont=dict(size=11),
                    hovertemplate="%{x}: <b>%{y} leads</b><extra></extra>",
                )
            )
            fig.update_layout(title="Leads por mês", height=320, showlegend=False, bargap=0.35)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ── Rankings do mês ──────────────────────────────────────────────
    col_b, col_i = st.columns(2)

    with col_b:
        st.markdown("#### Bairros mais procurados no mês")
        if leads_m.empty or leads_m["bairro"].dropna().empty:
            st.caption("Sem informação de bairro nos leads do mês.")
        else:
            top_b = (
                leads_m.dropna(subset=["bairro"]).groupby("bairro").size()
                .sort_values(ascending=False).head(8)
            )
            fig = go.Figure(
                go.Bar(
                    y=top_b.index.tolist()[::-1], x=top_b.values.tolist()[::-1],
                    orientation="h",
                    marker=dict(color=tema.COR_SERIE, cornerradius=4),
                    text=top_b.values.tolist()[::-1], textposition="outside",
                cliponaxis=False,
                    hovertemplate="%{y}: <b>%{x} leads</b><extra></extra>",
                )
            )
            fig.update_layout(height=300, showlegend=False, yaxis=dict(showgrid=False),
                              margin=dict(l=8, r=40, t=8, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_i:
        st.markdown("#### Imóveis mais procurados no mês")
        com_codigo = leads_m.dropna(subset=["codigo_imovel"]) if not leads_m.empty else pd.DataFrame()
        com_codigo = com_codigo[com_codigo["codigo_imovel"].astype(str).str.strip() != ""] if not com_codigo.empty else com_codigo
        if com_codigo.empty:
            st.caption(
                "Leads do mês sem código de imóvel vinculado — o webhook Jetimob→n8n ainda não "
                "grava esse campo. Enriquecer o workflow no n8n habilita este ranking."
            )
        else:
            top_i = com_codigo.groupby("codigo_imovel").size().sort_values(ascending=False).head(8)
            tab = top_i.rename("Leads").reset_index().rename(columns={"codigo_imovel": "Código do imóvel"})
            st.dataframe(tab, width="stretch", hide_index=True, height=300)

    # ── Aproveitamento por corretor ──────────────────────────────────
    st.markdown("#### Aproveitamento por corretor no mês")
    if leads_m.empty and (vendas_m is None or vendas_m.empty):
        st.caption("Sem dados no mês.")
    else:
        l_c = leads_m.dropna(subset=["corretor"]).groupby("corretor").size().rename("Leads recebidos") \
            if not leads_m.empty else pd.Series(dtype=int, name="Leads recebidos")
        v_c = vendas_m.groupby("corretor").size().rename("Fechamentos") \
            if not vendas_m.empty else pd.Series(dtype=int, name="Fechamentos")
        tab = pd.concat([l_c, v_c], axis=1).fillna(0).astype(int)
        tab = tab.sort_values(["Fechamentos", "Leads recebidos"], ascending=False)
        sem_atribuicao = int(tab["Leads recebidos"].sum()) == 0
        if sem_atribuicao:
            tab = tab.drop(columns=["Leads recebidos"])
        else:
            tab["Aproveitamento"] = tab.apply(
                lambda r: pct(r["Fechamentos"] / r["Leads recebidos"], 1) if r["Leads recebidos"] else "—",
                axis=1,
            )
        st.dataframe(tab.reset_index().rename(columns={"index": "Corretor", "corretor": "Corretor"}),
                     width="stretch", hide_index=True)
        if sem_atribuicao:
            st.caption("⚠️ Os leads do mês chegaram sem corretor atribuído no webhook — por enquanto a "
                       "tabela mostra só fechamentos. A atribuição por roleta fica registrada no Jetimob; "
                       "enriquecer o workflow n8n habilita o aproveitamento (leads → fechamentos).")
        else:
            st.caption("Leads recebidos = leads do Jetimob atribuídos ao corretor no mês. Fechamentos "
                       "incluem vendas e locações. Ciclos longos: fechamentos do mês podem vir de leads antigos.")

    # ── Lançamento manual de investimento ────────────────────────────
    st.divider()
    with st.expander("➕ Lançar investimento manual (quando não houver sync)"):
        st.caption("Registra gasto de mídia direto no banco (fonte 'manual'). Use total do dia ou do mês.")
        with st.form("investimento_manual"):
            f1, f2, f3 = st.columns(3)
            dia_lanc = f1.date_input("Dia (ou último dia do mês de referência)", value=hoje)
            plataforma = f2.selectbox("Plataforma", ["Meta Ads", "Google Ads"])
            valor = f3.number_input("Valor (R$)", min_value=0.0, step=50.0, format="%.2f")
            obs = st.text_input("Descrição (opcional)", placeholder="ex.: verba locação julho")
            ok = st.form_submit_button("Salvar", type="primary")
        if ok and valor > 0:
            try:
                inserir(
                    "ads_insights_daily",
                    [{
                        "dia": dia_lanc.isoformat(),
                        "plataforma": plataforma,
                        "campanha_id": f"manual-{dia_lanc.isoformat()}",
                        "campanha": obs or "(lançamento manual)",
                        "anuncio_id": f"manual-{dia_lanc.isoformat()}",
                        "spend": valor,
                        "fonte": "manual",
                    }],
                    on_conflict="dia,plataforma,anuncio_id,fonte",
                )
                st.cache_data.clear()
                st.success(f"Investimento de {brl(valor, 2)} registrado em {plataforma}.")
                st.rerun()
            except TabelaInexistente:
                st.error("Tabela `ads_insights_daily` ainda não existe — rode o "
                         "`sql/01_trafego_pago_schema.sql` no SQL Editor do Supabase primeiro.")
