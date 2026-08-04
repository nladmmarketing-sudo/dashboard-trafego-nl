"""Modelo 2 — Funil do Tráfego às Vendas (conexão tráfego + comercial).

Fluxo do período (leads → fechamentos, CAC, ROAS, VGV) e fotografia atual
do kanban do Jetimob por etapa.

Tudo nesta aba respeita o **setor** escolhido no topo (Todos / Vendas /
Locação): KPIs, VGV, investimento, kanban, fechamentos e ranking. Venda e
locação nunca são somados no mesmo número.

Limite conhecido: o webhook do Jetimob não informa o setor do lead, então
contagem de leads e conversão só existem na visão "Todos" (ver aviso).
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import dados, tema
from utils.formatos import brl, brl_compacto, nome_abreviado, num, pct

ROTULO_CONTRATO = {"venda": "Venda", "locacao": "Locação", "temporada": "Temporada"}
SETOR_CONTRATO = {"Vendas": "venda", "Locação": "locacao"}
COR_SETOR = {"Todos": tema.COR_SERIE, "Vendas": tema.COR_INVESTIMENTO, "Locação": tema.COR_RESULTADO}


def render(ctx: dict) -> None:
    ini, fim, canais = ctx["ini"], ctx["fim"], ctx["canais"]

    # ── Filtro de setor (governa a aba inteira) ──────────────────────
    st.markdown("#### Do lead ao fechamento — período selecionado")
    setor = st.radio(
        "Setor", ["Todos", "Vendas", "Locação"], horizontal=True, key="funil_setor",
        help="Separa a operação: Vendas (imóveis vendidos) × Locação (aluguéis). "
             "Afeta KPIs, VGV, investimento, kanban, fechamentos e ranking.",
    )
    tipo_alvo = {"Vendas": "Venda", "Locação": "Locação"}.get(setor)
    cor = COR_SETOR[setor]

    leads_per = dados.filtrar_canais(dados.filtrar_periodo(ctx["leads"], "dia", ini, fim), canais)
    vendas_tot = dados.filtrar_canais(dados.filtrar_periodo(ctx["vendas"], "data_venda", ini, fim), canais)
    # Fechamentos do setor — venda e locação nunca se misturam
    vendas_per = vendas_tot if tipo_alvo is None else vendas_tot[vendas_tot["tipo_negocio"] == tipo_alvo]

    # Investimento: recortado pelo setor da campanha
    ads = ctx["ads"]
    spend = None
    if ads is not None and not ads.empty:
        ads_per = dados.filtrar_periodo(ads, "dia", ini, fim)
        if tipo_alvo:
            ads_per = dados.filtrar_ads_por_setor(ads_per, tipo_alvo)
        spend = float(ads_per["spend"].sum()) if ads_per is not None and not ads_per.empty else 0.0

    v_venda = vendas_tot[vendas_tot["tipo_negocio"] == "Venda"]
    v_locac = vendas_tot[vendas_tot["tipo_negocio"] == "Locação"]
    vgv_venda = float(v_venda["valor"].fillna(0).sum())
    vgv_loc_mes = float(v_locac["valor"].fillna(0).sum())
    qtd_vendas, qtd_locacoes = len(v_venda), len(v_locac)
    fechamentos = len(vendas_per)

    # VGV do setor em foco (para ROAS/custo por VGV)
    vgv_foco = {"Vendas": vgv_venda, "Locação": vgv_loc_mes}.get(setor, vgv_venda + vgv_loc_mes)

    # ── KPIs ─────────────────────────────────────────────────────────
    # Leads não têm setor no Jetimob → só fazem sentido em "Todos".
    leads_ok = setor == "Todos"
    n_leads = len(leads_per)
    taxa_conv = (fechamentos / n_leads) if (leads_ok and n_leads) else None
    cac = (spend / fechamentos) if spend and fechamentos else None
    roas = (vgv_foco / spend) if spend and vgv_foco else None
    custo_vgv = (spend / vgv_foco) if spend and vgv_foco else None

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Leads", num(n_leads) if leads_ok else "—",
              help="Leads captados no período." if leads_ok else
                   "O webhook do Jetimob não informa se o lead é de venda ou locação, "
                   "então não dá para separar leads por setor. Veja em 'Todos'.")
    c2.metric(f"Fechamentos{'' if setor=='Todos' else f' · {setor}'}", num(fechamentos),
              help=f"{qtd_vendas} vendas + {qtd_locacoes} locações" if setor == "Todos"
                   else f"Somente {setor.lower()} no período.")
    c3.metric("Conversão lead→fechamento", pct(taxa_conv, 2) if taxa_conv is not None else "—",
              help="Fechamentos ÷ leads do período. Com ciclo longo, parte das vendas veio "
                   "de leads de meses anteriores." if leads_ok else
                   "Indisponível por setor (lead sem setor na origem).")
    c4.metric("Investimento (mídia)", brl(spend, 0) if spend is not None else "—",
              help="Mídia do período." + ("" if setor == "Todos" else
                   f" Só campanhas classificadas como {setor.lower()} (pelo nome da campanha)."))
    c5.metric("CAC (mídia)", brl(cac, 0) if cac else "—",
              help="Investimento ÷ fechamentos do setor.")
    c6.metric("ROAS (VGV)", f"{roas:.1f}×".replace(".", ",") if roas else "—",
              help="VGV do setor ÷ investimento do setor."
                   + (" Locação usa o aluguel mensal (não anualizado)." if setor == "Locação" else ""))

    if setor != "Todos":
        st.caption(f"🔎 Exibindo **somente {setor}** — fechamentos, VGV, investimento, kanban e "
                   "ranking abaixo consideram apenas este setor.")

    # ── VGV do setor ─────────────────────────────────────────────────
    n_meses = (fim.year - ini.year) * 12 + (fim.month - ini.month) + 1
    if setor in ("Todos", "Vendas"):
        vgv_venda_mes = (vgv_venda / n_meses) if n_meses else vgv_venda
    if setor == "Vendas":
        v1, v2, v3 = st.columns(3)
        v1.metric("💰 VGV Vendas (período)", brl(vgv_venda, 0), help=f"{qtd_vendas} vendas no período")
        v2.metric("💰 VGV Vendas (mês)", brl(vgv_venda_mes, 0),
                  help=f"Ritmo médio: VGV ÷ {n_meses} mês(es) do período")
        v3.metric("🎟️ Ticket médio", brl(vgv_venda / qtd_vendas, 0) if qtd_vendas else "—",
                  help="VGV ÷ nº de vendas")
    elif setor == "Locação":
        v1, v2, v3 = st.columns(3)
        v1.metric("🏠 VGV Locação (mês)", brl(vgv_loc_mes, 0),
                  help=f"{qtd_locacoes} locações · soma dos aluguéis mensais fechados")
        v2.metric("🏠 VGV Locação (ano)", brl(vgv_loc_mes * 12, 0),
                  help="Projeção anualizada (aluguel mensal × 12)")
        v3.metric("🎟️ Aluguel médio", brl(vgv_loc_mes / qtd_locacoes, 0) if qtd_locacoes else "—",
                  help="Soma dos aluguéis ÷ nº de locações")
    else:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("💰 VGV Vendas (período)", brl(vgv_venda, 0), help=f"{qtd_vendas} vendas no período")
        v2.metric("💰 VGV Vendas (mês)", brl(vgv_venda_mes, 0),
                  help=f"Ritmo médio: VGV ÷ {n_meses} mês(es)")
        v3.metric("🏠 VGV Locação (mês)", brl(vgv_loc_mes, 0), help=f"{qtd_locacoes} locações")
        v4.metric("🏠 VGV Locação (ano)", brl(vgv_loc_mes * 12, 0), help="Aluguel mensal × 12")
        st.caption("💡 Vendas e locação são **grandezas diferentes** (VGV de venda × aluguel mensal) — "
                   "por isso aparecem separados e nunca somados.")

    if spend is None:
        st.caption("💡 Investimento, CAC e ROAS aparecem quando houver mídia registrada "
                   "(sync do Meta/Google ou lançamento manual na aba Executivo).")

    st.divider()

    col_funil, col_kanban = st.columns([1, 1])

    # ── Fluxo do período ─────────────────────────────────────────────
    with col_funil:
        if leads_ok:
            etapas, valores = ["Leads captados", "Fechamentos"], [n_leads, fechamentos]
        else:
            etapas, valores = ["Fechamentos"], [fechamentos]
        fig = go.Figure(go.Funnel(
            y=etapas, x=valores,
            marker=dict(color=[tema.RAMPA_AZUL[2], cor][:len(etapas)] if leads_ok else [cor]),
            textinfo="value+percent initial" if leads_ok else "value",
            textfont=dict(size=14),
            connector=dict(line=dict(color=tema.HAIRLINE, width=1)),
            hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
        ))
        titulo = f"Fluxo do período ({ini.strftime('%d/%m')}–{fim.strftime('%d/%m')})"
        fig.update_layout(title=titulo + ("" if setor == "Todos" else f" · {setor}"),
                          height=340, showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Fluxo real do período: leads que entraram × negócios fechados."
                   if leads_ok else
                   "Leads não são separáveis por setor (origem sem essa informação) — "
                   "aqui só o total de fechamentos do setor.")

    # ── Kanban (estoque atual, por setor) ────────────────────────────
    with col_kanban:
        _render_kanban(ctx["funil"], setor)

    st.divider()

    # ── Conversão por canal ──────────────────────────────────────────
    st.markdown("#### Conversão por canal" + ("" if setor == "Todos" else f" · {setor}"))
    if leads_per.empty:
        st.caption("Sem leads no período.")
    else:
        lead_canal = leads_per.groupby("canal").size().rename("Leads")
        venda_canal = vendas_per.groupby("canal").size().rename("Fechamentos")
        base_vgv = vendas_per if setor != "Todos" else v_venda
        vgv_canal = base_vgv.groupby("canal")["valor"].sum().rename("VGV (R$)")
        tab = (pd.concat([lead_canal, venda_canal, vgv_canal], axis=1)
               .reindex(tema.ORDEM_CANAIS).dropna(how="all").fillna(0))
        tab["Leads"] = tab["Leads"].astype(int)
        tab["Fechamentos"] = tab["Fechamentos"].astype(int)
        tab["Conversão"] = tab.apply(
            lambda r: pct(r["Fechamentos"] / r["Leads"], 2) if r["Leads"] else "—", axis=1)
        tab["VGV (R$)"] = tab["VGV (R$)"].map(lambda v: brl(v) if v else "—")
        st.dataframe(tab.reset_index().rename(columns={"canal": "Canal"}),
                     width="stretch", hide_index=True)
        sem_origem = int(ctx["vendas"]["origem_lead"].isna().sum()) if "origem_lead" in ctx["vendas"] else 0
        total_v = len(ctx["vendas"])
        if sem_origem:
            st.caption(f"⚠️ {sem_origem} de {total_v} fechamentos estão sem origem preenchida no Jetimob — "
                       "cobrar o preenchimento no fechamento melhora esta análise."
                       + ("" if leads_ok else " Os leads da coluna não são separados por setor."))

    # ── Fechamentos + ranking ────────────────────────────────────────
    col_v, col_r = st.columns([3, 2])

    with col_v:
        st.markdown(f"#### Fechamentos no período{'' if setor=='Todos' else f' · {setor}'}")
        if vendas_per.empty:
            st.caption(f"Nenhum fechamento{'' if setor=='Todos' else f' de {setor.lower()}'} no período.")
        else:
            if setor == "Todos":
                st.caption(f"💰 {qtd_vendas} venda(s) · {brl(vgv_venda, 0)}  |  "
                           f"🏠 {qtd_locacoes} locação(ões) · {brl(vgv_loc_mes, 0)}/mês".replace("$", "\\$"))
            tab_v = vendas_per.sort_values(["tipo_negocio", "data_venda"], ascending=[True, False]).copy()
            tab_v["Data"] = tab_v["data_venda"].map(lambda d: d.strftime("%d/%m/%Y"))
            tab_v["Cliente"] = tab_v["nome_cliente"].map(nome_abreviado)
            tab_v["Código"] = tab_v.get("codigo_imovel", "").map(
                lambda c: str(c).strip() if pd.notna(c) and str(c).strip() else "—")
            tab_v["Valor"] = tab_v["valor"].map(lambda v: brl(v) if pd.notna(v) else "—")
            cols = ["Data", "Cliente", "Código", "tipo_negocio", "Valor", "corretor", "origem_lead"]
            nomes = ["Data", "Cliente", "Código", "Tipo", "Valor", "Corretor", "Origem"]
            if setor != "Todos":  # tipo é redundante quando já filtrado
                cols.remove("tipo_negocio"); nomes.remove("Tipo")
            tab_v = tab_v[cols]
            tab_v.columns = nomes
            st.dataframe(tab_v, width="stretch", hide_index=True, height=320)

    with col_r:
        st.markdown(f"#### Ranking de corretores{'' if setor=='Todos' else f' · {setor}'}")
        if vendas_per.empty:
            st.caption("—")
        else:
            rank = (vendas_per.assign(corretor=vendas_per["corretor"].fillna("(sem corretor)"))
                    .groupby("corretor")
                    .agg(Fechamentos=("corretor", "size"), VGV=("valor", "sum"))
                    .sort_values(["Fechamentos", "VGV"], ascending=False).head(8))
            fig = go.Figure(go.Bar(
                y=rank.index.tolist()[::-1], x=rank["Fechamentos"].tolist()[::-1],
                orientation="h", marker=dict(color=cor, cornerradius=4),
                text=[f"{f}  ·  {brl_compacto(v)}" for f, v in
                      zip(rank["Fechamentos"].tolist()[::-1], rank["VGV"].tolist()[::-1])],
                textposition="outside", cliponaxis=False,
                hovertemplate="%{y}: <b>%{x} fechamento(s)</b><extra></extra>",
            ))
            fig.update_layout(height=300, showlegend=False,
                              xaxis=dict(showgrid=True), yaxis=dict(showgrid=False),
                              margin=dict(l=8, r=80, t=8, b=8))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption("Barra = nº de fechamentos · texto = fechamentos · VGV"
                       + ("" if setor == "Todos" else f" · somente {setor.lower()}"))


def _render_kanban(funil, setor: str) -> None:
    """Estoque atual do kanban do Jetimob, sempre de um contrato por vez."""
    if funil is None:
        st.markdown(
            "<div style='height:340px;border:1px dashed #dfdfdf;border-radius:12px;"
            "color:#9a9a9a;padding:24px;display:flex;flex-direction:column;"
            "align-items:center;justify-content:center;text-align:center;gap:8px'>"
            "<span>Fotografia do kanban aparece aqui após rodar</span>"
            "<code>~/.jetimob-scraper/relogar.sh</code></div>",
            unsafe_allow_html=True,
        )
        return

    df_funil, snapshot_em = funil
    contratos = sorted(df_funil["contrato"].unique().tolist())

    # O setor escolhido no topo manda; em "Todos" o usuário escolhe o contrato.
    alvo = SETOR_CONTRATO.get(setor)
    if alvo and alvo in contratos:
        contrato, escolhido = alvo, ROTULO_CONTRATO[alvo]
    else:
        rotulos = [ROTULO_CONTRATO.get(c, c.title()) for c in contratos]
        escolhido = st.radio("Kanban", rotulos, horizontal=True,
                             label_visibility="collapsed", key="kanban_contrato")
        contrato = contratos[rotulos.index(escolhido)]

    sub = df_funil[df_funil["contrato"] == contrato].sort_values("posicao_etapa")
    total = int(sub["qtd"].sum())
    valor_total = float(sub["valor_total"].sum())

    if total == 0:
        st.info(f"Kanban de {escolhido}: nenhuma oportunidade aberta no último snapshot.")
        st.caption(f"Fotografia de {snapshot_em.strftime('%d/%m/%Y %H:%M')}.")
        return

    n = max(len(sub), 1)
    cores = [tema.RAMPA_AZUL[min(int(i * (len(tema.RAMPA_AZUL) - 1) / max(n - 1, 1)),
                                 len(tema.RAMPA_AZUL) - 1)] for i in range(n)]
    fig = go.Figure(go.Funnel(
        y=sub["etapa"].tolist(), x=sub["qtd"].tolist(),
        marker=dict(color=cores), textinfo="value+percent initial",
        customdata=sub["valor_total"].tolist(),
        connector=dict(line=dict(color=tema.HAIRLINE, width=1)),
        hovertemplate="%{y}: <b>%{x} oportunidades</b><br>R$ %{customdata:,.0f} em jogo<extra></extra>",
    ))
    fig.update_layout(title=f"Kanban agora — {escolhido} ({num(total)} abertas)",
                      height=300, showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    fechamento = sub[sub["etapa"].str.contains("fechamento", case=False, na=False)]["qtd"].sum()
    st.caption(
        f"📸 Fotografia de **{snapshot_em.strftime('%d/%m/%Y %H:%M')}** · estoque de "
        f"**{num(total)}** oportunidades abertas de {escolhido.lower()} "
        f"(**{brl_compacto(valor_total)}** em jogo, {num(int(fechamento))} em fechamento). "
        "É estoque acumulado, não fluxo do período — e nunca mistura venda com locação."
    )
