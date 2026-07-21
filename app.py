"""Dashboard de Tráfego Pago — NL Imóveis (CRECI 1440 J, Natal/RN).

Conecta o dinheiro investido (Meta/Google) com leads do Jetimob e
negócios fechados. Três visões: dia a dia do gestor, funil → vendas
e resumo executivo para diretoria.

Deploy: Streamlit Community Cloud (share.streamlit.io). Ver README.md.
"""

import hmac

import streamlit as st

from utils import dados, tema
from views import executivo, funil_vendas, investimento, visao_geral

st.set_page_config(
    page_title="Tráfego Pago — NL Imóveis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

tema.registrar_template_plotly()
tema.injetar_css()


# ── Gate de acesso ───────────────────────────────────────────────────
# Senha única definida em st.secrets["app"]["senha"]. O painel expõe
# VGV e nomes de clientes — nunca publicar sem senha (LGPD).

def _autenticado() -> bool:
    try:
        senha_config = st.secrets["app"]["senha"]
    except (KeyError, FileNotFoundError):
        st.warning(
            "⚠️ Nenhuma senha configurada em `[app] senha` nos secrets — "
            "painel aberto. Configure antes de divulgar o link."
        )
        return True

    if st.session_state.get("auth_ok"):
        return True

    st.markdown("## 📊 Tráfego Pago — NL Imóveis")
    st.caption("Acesso restrito. Informe a senha para continuar.")
    with st.form("login"):
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary")
    if entrar:
        if hmac.compare_digest(senha, senha_config):
            st.session_state["auth_ok"] = True
            st.rerun()
        st.error("Senha incorreta.")
    return False


if not _autenticado():
    st.stop()


# ── Sidebar: filtros globais ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 NL Imóveis")
    st.caption("Tráfego Pago & Performance")

    opcao_periodo = st.radio("Período", dados.OPCOES_PERIODO, index=1)
    ini_custom = fim_custom = None
    if opcao_periodo == "Personalizado":
        col_a, col_b = st.columns(2)
        ini_custom = col_a.date_input("De", value=dados.hoje_local().replace(day=1))
        fim_custom = col_b.date_input("Até", value=dados.hoje_local())
    ini, fim = dados.intervalo_periodo(opcao_periodo, ini_custom, fim_custom)

    canais_sel = st.multiselect(
        "Canais",
        tema.ORDEM_CANAIS,
        default=tema.ORDEM_CANAIS,
        help="Origem do lead classificada em canal de mídia (ver README).",
    )

    st.divider()
    if st.button("🔄 Atualizar dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Janela: {ini.strftime('%d/%m/%Y')} — {fim.strftime('%d/%m/%Y')}")
    if st.session_state.get("auth_ok") and st.button("Sair", width="stretch"):
        st.session_state["auth_ok"] = False
        st.rerun()


# ── Carga de dados (cache 10 min) ────────────────────────────────────
with st.spinner("Carregando dados do Supabase…"):
    leads = dados.carregar_leads()
    vendas = dados.carregar_vendas()
    resumo_mensal = dados.carregar_resumo_mensal()
    ads = dados.carregar_ads()          # None = schema pendente
    funil = dados.carregar_funil()      # None = sem snapshot
    custos = dados.carregar_custos()    # None = tabela custos pendente

ctx = {
    "ini": ini,
    "fim": fim,
    "canais": canais_sel,
    "leads": leads,
    "vendas": vendas,
    "resumo_mensal": resumo_mensal,
    "ads": ads,
    "funil": funil,
    "custos": custos,
}

st.markdown("## Tráfego Pago — NL Imóveis")

aba1, aba2, aba3, aba4 = st.tabs(
    ["📈  Visão Geral", "🔀  Funil → Vendas", "🏛️  Executivo", "💰  Investimento"]
)
with aba1:
    visao_geral.render(ctx)
with aba2:
    funil_vendas.render(ctx)
with aba3:
    executivo.render(ctx)
with aba4:
    investimento.render(ctx)

st.caption(
    "Fontes: leads via webhook Jetimob→n8n (tempo real) · vendas via sync diário do kanban Jetimob · "
    "investimento via Meta/Google (sync) ou lançamento manual · fuso America/Fortaleza · cache 10 min."
)
