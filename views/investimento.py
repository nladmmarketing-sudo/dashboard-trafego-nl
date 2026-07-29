"""Aba Investimento em Marketing — CAC real + boletos e avisos financeiros.

Soma a mídia paga (Meta/Google, automática) com os custos (plataforma/CRM,
portais, ferramentas) para o CAC real. Inclui a gestão financeira de custos
por periodicidade (mensal/anual/variável), controle de boletos a pagar/pagos
e avisos (retirar boletos mensais, revisar planos anuais).
"""

import calendar
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

ALERTA_DIAS = 5            # aviso mensal: X dias antes do vencimento
ALERTA_ANUAL_DIAS = 45    # janela para lembrar de revisar planos anuais
ROT_PERIOD = {"mensal": "Mensal", "anual": "Anual", "variavel": "Variável"}
ROT_SETOR = {"geral": "Geral", "venda": "Venda", "locacao": "Locação"}


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


# ── Boletos ──────────────────────────────────────────────────────────

def _boleto_venc(r, mes: date):
    """Data de vencimento do boleto de r no 'mes', ou None se não é devido nele."""
    per = r.get("periodicidade") or "mensal"
    last = calendar.monthrange(mes.year, mes.month)[1]
    if per == "mensal":
        dia = r.get("dia_vencimento")
        if dia is None or pd.isna(dia):
            return None
        return date(mes.year, mes.month, min(int(dia), last))
    dv = r.get("data_vencimento")
    if dv is None or pd.isna(dv):
        return None
    if per == "anual":            # recorre todo ano no mesmo mês
        if dv.month == mes.month:
            return date(mes.year, dv.month, min(dv.day, last))
        return None
    if dv.year == mes.year and dv.month == mes.month:   # variável: mês+ano exatos
        return dv
    return None


def _boletos_do_mes(custos, pagamentos, mes: date) -> list[dict]:
    if custos is None or custos.empty:
        return []
    aplic = dados.custos_do_mes(custos, mes)
    if aplic is None or aplic.empty:
        return []
    comp = mes.replace(day=1)
    pagos = {}
    if pagamentos is not None and not pagamentos.empty:
        for _, p in pagamentos.iterrows():
            if p["competencia"] == comp and pd.notna(p["custo_id"]):
                pagos[int(p["custo_id"])] = p
    out = []
    for _, r in aplic.iterrows():
        per = r.get("periodicidade") or "mensal"
        venc = _boleto_venc(r, mes)
        if per != "mensal" and venc is None:
            continue   # anual/variável só aparecem no mês do vencimento
        cid = int(r["id"])
        val = r.get("valor_pagamento")
        if val is None or pd.isna(val):
            val = r["valor_mensal"]
        pg = pagos.get(cid)
        out.append({
            "custo_id": cid, "item": r["item"], "categoria": r["categoria"],
            "periodicidade": per, "valor": float(val), "vencimento": venc,
            "pago": pg is not None,
            "data_pagamento": (pg["data_pagamento"] if pg is not None else None),
        })
    return out


def _anuais_a_revisar(custos, hoje: date) -> list[tuple]:
    """Custos anuais cuja próxima renovação está dentro da janela de alerta."""
    if custos is None or custos.empty:
        return []
    out = []
    for _, r in custos.iterrows():
        if not bool(r.get("ativo", True)) or (r.get("periodicidade") or "mensal") != "anual":
            continue
        dv = r.get("data_vencimento")
        if dv is None or pd.isna(dv):
            continue
        prox = date(hoje.year, dv.month, min(dv.day, 28))
        if prox < hoje:
            prox = date(hoje.year + 1, dv.month, min(dv.day, 28))
        if (prox - hoje).days <= ALERTA_ANUAL_DIAS:
            val = r.get("valor_pagamento")
            if val is None or pd.isna(val):
                val = r["valor_mensal"] * 12
            out.append((r["item"], prox, float(val)))
    return sorted(out, key=lambda x: x[1])


def _secao_boletos(custos, pagamentos, mes: date, hoje: date):
    boletos = _boletos_do_mes(custos, pagamentos, mes)
    st.markdown("#### 🧾 Boletos & avisos")
    if not boletos:
        st.caption("Nenhum boleto no mês. Cadastre os custos com vencimento na gestão de custos abaixo.")
        return

    a_pagar = [b for b in boletos if not b["pago"]]
    pagos = [b for b in boletos if b["pago"]]
    total_pagar = sum(b["valor"] for b in a_pagar)
    total_pago = sum(b["valor"] for b in pagos)

    def _sit(b):
        v = b["vencimento"]
        if v is None:
            return "sem_data"
        if v < hoje:
            return "vencido"
        if v <= hoje + timedelta(days=ALERTA_DIAS):
            return "vencendo"
        return "futuro"

    venc_soon = [b for b in a_pagar if _sit(b) in ("vencido", "vencendo")]

    # aviso mensal — retirar/pagar boletos
    if venc_soon:
        linhas = "\n".join(
            f"- **{b['item']}** — {brl(b['valor'], 2)} · "
            f"{'⛔ venceu em' if _sit(b) == 'vencido' else '⏰ vence'} "
            f"{b['vencimento'].strftime('%d/%m') if b['vencimento'] else ''}"
            for b in sorted(venc_soon, key=lambda x: (x["vencimento"] or date.max))
        )
        st.warning(
            f"**Retirar e pagar boletos** — {len(venc_soon)} boleto(s) vencidos ou "
            f"vencendo em até {ALERTA_DIAS} dias:\n\n{linhas}", icon="🔔")

    # aviso anual — revisar planos
    anuais = _anuais_a_revisar(custos, hoje)
    if anuais:
        linhas = "\n".join(
            f"- **{it}** renova em {d.strftime('%d/%m/%Y')} — {brl(v, 2)}/ano"
            for it, d, v in anuais)
        st.info(
            "**Revisar planos anuais** — conferir se houve reajuste antes de renovar:\n\n"
            f"{linhas}", icon="🗓️")

    # KPIs de boletos
    b1, b2, b3 = st.columns(3)
    b1.metric("🔴 A pagar no mês", brl(total_pagar, 2), help=f"{len(a_pagar)} boleto(s) em aberto")
    b2.metric("🟢 Pagos no mês", brl(total_pago, 2), help=f"{len(pagos)} boleto(s) quitados")
    b3.metric("Total de boletos", brl(total_pagar + total_pago, 2), help="A pagar + pagos no mês")

    # lista a pagar (com botão marcar pago)
    if a_pagar:
        st.markdown("###### A pagar")
        for b in sorted(a_pagar, key=lambda x: (x["vencimento"] or date.max)):
            c = st.columns([3, 1.2, 1.4, 1.1])
            venc_txt = b["vencimento"].strftime("%d/%m/%Y") if b["vencimento"] else "— a definir"
            marca = "🔴" if _sit(b) == "vencido" else ("🟡" if _sit(b) == "vencendo" else "⚪")
            c[0].write(f"{marca} **{b['item']}** · {b['categoria']} · {ROT_PERIOD.get(b['periodicidade'], '')}")
            c[1].write(brl(b["valor"], 2))
            c[2].write(f"venc. {venc_txt}")
            if c[3].button("✅ Pago", key=f"pg_{b['custo_id']}_{mes.isoformat()}", use_container_width=True):
                try:
                    inserir("pagamentos", [{
                        "custo_id": b["custo_id"],
                        "competencia": mes.replace(day=1).isoformat(),
                        "valor_pago": b["valor"],
                        "data_pagamento": dados.hoje_local().isoformat(),
                    }], on_conflict="custo_id,competencia")
                    st.cache_data.clear()
                    st.success(f"{b['item']} marcado como pago.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao marcar pago: {e}")
    else:
        st.success("Todos os boletos do mês estão pagos. 🎉")

    # lista pagos
    if pagos:
        with st.expander(f"✅ Pagos no mês ({len(pagos)}) — {brl(total_pago, 2)}"):
            for b in sorted(pagos, key=lambda x: x["item"]):
                dp = b["data_pagamento"].strftime("%d/%m/%Y") if b["data_pagamento"] else "—"
                cols = st.columns([3, 1.2, 1.4, 1.1])
                cols[0].write(f"🟢 **{b['item']}** · {b['categoria']}")
                cols[1].write(brl(b["valor"], 2))
                cols[2].write(f"pago em {dp}")
                if cols[3].button("↩️ Desfazer", key=f"un_{b['custo_id']}_{mes.isoformat()}",
                                  use_container_width=True):
                    try:
                        _desmarcar_pago(b["custo_id"], mes)
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")


def _desmarcar_pago(custo_id: int, mes: date):
    """Remove o registro de pagamento do custo naquele mês."""
    import os
    import urllib.request
    base = st.secrets["supabase"]["url"].rstrip("/")
    key = st.secrets["supabase"]["key"]
    comp = mes.replace(day=1).isoformat()
    url = f"{base}/rest/v1/pagamentos?custo_id=eq.{custo_id}&competencia=eq.{comp}"
    req = urllib.request.Request(url, method="DELETE",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    urllib.request.urlopen(req, timeout=20)


def render(ctx: dict) -> None:
    custos = ctx.get("custos")
    pagamentos = ctx.get("pagamentos")
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

    # ── Boletos & avisos ─────────────────────────────────────────────
    if custos is not None:
        _secao_boletos(custos, pagamentos, mes, hoje)
        st.divider()

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

    # ── Gestão de custos (financeiro) ────────────────────────────────
    st.divider()
    if custos is None:
        st.markdown("#### Gestão de custos")
        st.caption("Disponível após criar a tabela `custos_marketing`.")
        return

    _gestao_custos(custos)


def _fmt_venc(r) -> str:
    per = r.get("periodicidade") or "mensal"
    if per == "mensal":
        d = r.get("dia_vencimento")
        return f"todo dia {int(d)}" if (d is not None and pd.notna(d) and d) else "— a definir"
    dv = r.get("data_vencimento")
    return dv.strftime("%d/%m/%Y") if (dv is not None and pd.notna(dv)) else "— a definir"


def _gestao_custos(custos: pd.DataFrame):
    st.markdown("#### 💼 Gestão de custos (financeiro)")
    st.caption("A gestora financeira lança aqui os custos por periodicidade, com valor do boleto "
               "e data de vencimento. Isso alimenta os avisos e o CAC real.")

    ativos = custos[custos["ativo"]] if not custos.empty else custos
    if ativos is not None and not ativos.empty:
        # resumo por periodicidade
        res = ativos.copy()
        res["_vp"] = res.apply(lambda r: r.get("valor_pagamento") if pd.notna(r.get("valor_pagamento")) else r["valor_mensal"], axis=1)
        r1, r2, r3 = st.columns(3)
        for col, per in zip((r1, r2, r3), ("mensal", "anual", "variavel")):
            sub = res[res["periodicidade"] == per]
            col.metric(f"{ROT_PERIOD[per]} ({len(sub)})", brl(sub["_vp"].sum(), 2))

        tab = ativos.copy()
        tab["Periodicidade"] = tab["periodicidade"].map(lambda p: ROT_PERIOD.get(p, p))
        tab["Valor boleto"] = tab.apply(
            lambda r: brl(r.get("valor_pagamento") if pd.notna(r.get("valor_pagamento")) else r["valor_mensal"], 2), axis=1)
        tab["Vencimento"] = tab.apply(_fmt_venc, axis=1)
        tab["Setor"] = tab["setor"].map(lambda s: ROT_SETOR.get(s, "—") if s else "—")
        show = tab[["categoria", "item", "Periodicidade", "Valor boleto", "Vencimento", "Setor"]].rename(
            columns={"categoria": "Categoria", "item": "Item"})
        st.dataframe(show, width="stretch", hide_index=True)
    else:
        st.caption("Nenhum custo cadastrado ainda. Adicione abaixo 👇")

    with st.expander("➕ Lançar custo"):
        with st.form("add_custo"):
            f1, f2, f3, f4 = st.columns([1.1, 1.6, 1, 1])
            categoria = f1.selectbox("Categoria", dados.CATEGORIAS_CUSTO)
            item = f2.text_input("Item", placeholder="ex.: Jetimob, Canal Pró, n8n")
            periodicidade = f3.selectbox("Periodicidade", dados.PERIODICIDADES,
                                         format_func=lambda p: ROT_PERIOD[p])
            setor = f4.selectbox("Setor", dados.SETORES_CUSTO, format_func=lambda s: ROT_SETOR[s])
            g1, g2, g3 = st.columns(3)
            valor = g1.number_input("Valor do boleto (R$)", min_value=0.0, step=50.0, format="%.2f")
            dia = g2.number_input("Dia venc. (se mensal)", min_value=0, max_value=31, step=1)
            data_v = g3.date_input("Data venc. (anual/variável)", value=None, format="DD/MM/YYYY")
            obs = st.text_input("Observação (opcional)")
            ok = st.form_submit_button("Salvar custo", type="primary")
        if ok and item.strip() and valor > 0:
            vm = valor if periodicidade == "mensal" else (valor / 12 if periodicidade == "anual" else valor)
            payload = {
                "categoria": categoria, "item": item.strip(),
                "valor_mensal": round(vm, 2), "valor_pagamento": valor,
                "periodicidade": periodicidade, "setor": setor,
                "mes_inicio": dados.hoje_local().replace(day=1).isoformat(),
                "ativo": True, "obs": obs or None,
            }
            if periodicidade == "mensal" and dia > 0:
                payload["dia_vencimento"] = int(dia)
            if periodicidade in ("anual", "variavel") and data_v:
                payload["data_vencimento"] = data_v.isoformat()
            try:
                inserir("custos_marketing", [payload], on_conflict="categoria,item,mes_inicio")
                st.cache_data.clear()
                st.success(f"{item} lançado ({ROT_PERIOD[periodicidade]}, {brl(valor, 2)}).")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    if ativos is not None and not ativos.empty:
        with st.expander("✏️ Editar custo · definir vencimento · encerrar"):
            opcoes = {f"{r['item']} — {ROT_PERIOD.get(r['periodicidade'], '')} · "
                      f"{brl(r.get('valor_pagamento') if pd.notna(r.get('valor_pagamento')) else r['valor_mensal'], 2)}": r["id"]
                      for _, r in ativos.iterrows()}
            escolha = st.selectbox("Custo", list(opcoes.keys()), key="edit_custo_sel")
            cid = opcoes[escolha]
            row = ativos[ativos["id"] == cid].iloc[0]
            per = row.get("periodicidade") or "mensal"
            valor_atual = float(row.get("valor_pagamento") if pd.notna(row.get("valor_pagamento")) else row["valor_mensal"])

            e1, e2, e3 = st.columns(3)
            novo_valor = e1.number_input("Valor do boleto (R$)", min_value=0.0, step=50.0,
                                         format="%.2f", value=valor_atual)
            dia_atual = int(row["dia_vencimento"]) if pd.notna(row.get("dia_vencimento")) else 0
            novo_dia = e2.number_input("Dia venc. (se mensal)", min_value=0, max_value=31,
                                       step=1, value=dia_atual)
            data_atual = row.get("data_vencimento") if pd.notna(row.get("data_vencimento")) else None
            nova_data = e3.date_input("Data venc. (anual/variável)", value=data_atual, format="DD/MM/YYYY")

            cA, cB = st.columns(2)
            salvar = cA.button("💾 Salvar", use_container_width=True, key="save_custo_btn")
            encerrar = cB.button("🚫 Encerrar custo", use_container_width=True, key="end_custo_btn",
                                 help="Para de contar nos próximos meses")
            if salvar and novo_valor > 0:
                vm = novo_valor if per == "mensal" else (novo_valor / 12 if per == "anual" else novo_valor)
                upd = {"valor_pagamento": novo_valor, "valor_mensal": round(vm, 2),
                       "atualizado_em": "now()"}
                if per == "mensal":
                    upd["dia_vencimento"] = int(novo_dia) if novo_dia > 0 else None
                else:
                    upd["data_vencimento"] = nova_data.isoformat() if nova_data else None
                atualizar("custos_marketing", cid, upd)
                st.cache_data.clear()
                st.success("Custo atualizado.")
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
