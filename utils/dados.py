"""Camada de dados: carrega tabelas do Supabase, classifica origens em
canais de mídia e resolve janelas de período (fuso America/Fortaleza).

Fontes:
- leads_jetimob        → leads em tempo real (webhook Jetimob → n8n)
- vendas_nl            → negócios fechados (sync diário via kanban Jetimob)
- resumo_mensal_jetimob→ totais oficiais do relatório do Jetimob (vendas)
- ads_insights_daily   → investimento Meta/Google (sync_meta_ads.py ou manual)
- funil_snapshot       → fotografia do kanban por etapa (sync_funil_jetimob.py)
"""

import os
import unicodedata
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from utils.supabase import TabelaInexistente, buscar_tabela

TZ = "America/Fortaleza"

# ── Canais ───────────────────────────────────────────────────────────

_PORTAIS = ("zap", "viva", "olx", "chaves", "imovelweb", "imovel web", "123i", "portal")
_META = ("face", "insta", "meta", "fb ")
_GOOGLE = ("google", "gads", "youtube", "pmax", "performance max")


def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


def mapear_canal(origem: str | None) -> str:
    o = _normalizar(origem)
    if not o:
        return "Direto/Outros"
    if any(p in o for p in _PORTAIS):
        return "Portais"
    if "site" in o:
        return "Site NL"
    if any(p in o for p in _META):
        return "Meta Ads"
    if any(p in o for p in _GOOGLE):
        return "Google Ads"
    return "Direto/Outros"


# ── Períodos ─────────────────────────────────────────────────────────

OPCOES_PERIODO = [
    "Últimos 7 dias",
    "Últimos 30 dias",
    "Últimos 90 dias",
    "Mês atual",
    "Mês anterior",
    "Personalizado",
]


def hoje_local() -> date:
    return pd.Timestamp.now(tz=TZ).date()


def intervalo_periodo(opcao: str, ini_custom: date | None = None, fim_custom: date | None = None) -> tuple[date, date]:
    hoje = hoje_local()
    if opcao == "Últimos 7 dias":
        return hoje - timedelta(days=6), hoje
    if opcao == "Últimos 30 dias":
        return hoje - timedelta(days=29), hoje
    if opcao == "Últimos 90 dias":
        return hoje - timedelta(days=89), hoje
    if opcao == "Mês atual":
        return hoje.replace(day=1), hoje
    if opcao == "Mês anterior":
        fim_mes_ant = hoje.replace(day=1) - timedelta(days=1)
        return fim_mes_ant.replace(day=1), fim_mes_ant
    return ini_custom or hoje - timedelta(days=29), fim_custom or hoje


def janela_anterior(ini: date, fim: date) -> tuple[date, date]:
    """Janela imediatamente anterior com a mesma duração (para os deltas)."""
    dur = (fim - ini).days + 1
    return ini - timedelta(days=dur), ini - timedelta(days=1)


# ── Loaders ──────────────────────────────────────────────────────────

def carregar_leads() -> pd.DataFrame:
    linhas = buscar_tabela(
        "leads_jetimob",
        select="created_at,origem,corretor,bairro,cidade,valor,codigo_imovel",
    )
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=["dia", "origem", "canal", "corretor", "bairro", "cidade", "valor", "codigo_imovel"])
    dt = pd.to_datetime(df["created_at"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    df["dia"] = dt.dt.date
    df["origem"] = df["origem"].fillna("").replace("", "(sem origem)")
    df["canal"] = df["origem"].map(mapear_canal)
    df["bairro"] = df["bairro"].fillna("").str.strip().replace("", None)
    df["corretor"] = df["corretor"].fillna("").str.strip().replace("", None)
    return df


def carregar_vendas() -> pd.DataFrame:
    linhas = buscar_tabela(
        "vendas_nl",
        select="data_venda,nome_cliente,tipo_negocio,tipo_imovel,codigo_imovel,bairro,valor,corretor,origem_lead",
        filtros="comprou_com_nl=eq.true",
    )
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(
            columns=["data_venda", "nome_cliente", "tipo_negocio", "tipo_imovel",
                     "codigo_imovel", "bairro", "valor", "corretor", "origem_lead", "canal"]
        )
    df["data_venda"] = pd.to_datetime(df["data_venda"]).dt.date
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["canal"] = df["origem_lead"].map(mapear_canal)
    # tipo_negocio chega inconsistente ('Venda', 'venda', 'locação', 'aluguel'…)
    def _tipo(t):
        t = _normalizar(t)
        if "vend" in t:
            return "Venda"
        if "loca" in t or "alug" in t:
            return "Locação"
        if "tempor" in t:
            return "Temporada"
        return "Outro"
    df["tipo_negocio"] = df["tipo_negocio"].map(_tipo)
    return df


def carregar_resumo_mensal() -> pd.DataFrame:
    linhas = buscar_tabela(
        "resumo_mensal_jetimob",
        select="mes_referencia,tipo,qtd_ganhas,valor_total_cents,scraped_at",
    )
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=["mes", "tipo", "qtd", "valor", "scraped_at"])
    df["mes"] = pd.to_datetime(df["mes_referencia"]).dt.date
    df["qtd"] = df["qtd_ganhas"].fillna(0).astype(int)
    df["valor"] = df["valor_total_cents"].fillna(0) / 100.0
    return df[["mes", "tipo", "qtd", "valor", "scraped_at"]]


_COLS_ADS = ["dia", "plataforma", "conta", "campanha_id", "campanha", "conjunto",
             "anuncio_id", "anuncio", "objetivo", "spend", "impressoes", "alcance",
             "cliques", "cliques_link", "leads", "mensagens", "video_plays", "fonte"]


def carregar_ads() -> pd.DataFrame | None:
    """None = tabela ainda não criada (schema pendente).

    Com DEMO_ADS=1 no ambiente, devolve um dataset fictício de Meta Ads
    (padrão imobiliário) para pré-visualizar o layout antes do sync real.
    """
    if os.getenv("DEMO_ADS") == "1":
        return _ads_demo()
    try:
        linhas = buscar_tabela("ads_insights_daily")
    except TabelaInexistente:
        return None
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=_COLS_ADS)
    df["dia"] = pd.to_datetime(df["dia"]).dt.date
    for c in ("spend", "impressoes", "alcance", "cliques", "cliques_link",
              "leads", "mensagens", "video_plays"):
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in ("campanha", "conjunto", "anuncio", "objetivo", "plataforma",
              "conta", "campanha_id", "anuncio_id", "fonte"):
        if c not in df.columns:
            df[c] = ""
    return df


def _ads_demo() -> pd.DataFrame:
    """Meta + Google Ads fictício, 90 dias, nível anúncio (preview do layout imobiliário)."""
    import numpy as np

    rng = np.random.default_rng(42)
    fim = hoje_local()
    ini = fim - timedelta(days=89)
    dias = pd.date_range(ini, fim, freq="D").date

    # (plataforma, campanha, objetivo, peso, [(anúncio/criativo, conjunto), ...])
    campanhas = [
        ("Meta Ads", "Lançamento Alto Padrão | Ponta Negra", "leads", 1.6,
         [("Vídeo tour cobertura", "LAL 1% RN"), ("Carrossel plantas", "Interesses lançamento")]),
        ("Meta Ads", "Apartamentos 2-3 quartos | Capim Macio", "leads", 1.3,
         [("Foto fachada + preço", "Capim Macio 3km"), ("Reels visita guiada", "Remarketing site")]),
        ("Meta Ads", "Captação Proprietários | Locação", "leads", 0.9,
         [("Anuncie seu imóvel", "Proprietários ZN")]),
        ("Meta Ads", "Remarketing Site | Todos", "mensagens", 0.7,
         [("Fale no WhatsApp", "Visitantes 30d")]),
        ("Google Ads", "Search | Apartamento Natal", "leads", 1.2,
         [("Apartamentos à venda Natal", "Termos genéricos"),
          ("Apto Ponta Negra | NL", "Termos bairro")]),
        ("Google Ads", "PMax | Imóveis NL", "leads", 1.0,
         [("Performance Max NL", "Todos os produtos")]),
    ]
    linhas = []
    for plataforma, c_nome, obj, peso, anuncios in campanhas:
        conta = "act_476390709618184" if plataforma == "Meta Ads" else "NL Imóveis (Google Ads)"
        for a_idx, (a_nome, conjunto) in enumerate(anuncios):
            base_spend = 45 * peso / len(anuncios) * rng.uniform(0.7, 1.3)
            for i, d in enumerate(dias):
                sazonal = 1 + 0.25 * np.sin(i / 6.0) + rng.normal(0, 0.12)
                sazonal = max(sazonal, 0.35)
                spend = round(base_spend * sazonal, 2)
                imp_fator = rng.uniform(120, 190) if plataforma == "Meta Ads" else rng.uniform(45, 80)
                impressoes = int(spend * imp_fator)
                alcance = int(impressoes * rng.uniform(0.55, 0.72))
                ctr = rng.uniform(0.008, 0.016) if plataforma == "Meta Ads" else rng.uniform(0.03, 0.06)
                cliques = int(impressoes * ctr)
                cliques_link = int(cliques * rng.uniform(0.7, 0.9))
                if obj == "leads":
                    leads = max(int(cliques_link * rng.uniform(0.06, 0.13)), 0)
                    mensagens = max(int(cliques_link * rng.uniform(0.02, 0.05)), 0)
                else:
                    mensagens = max(int(cliques_link * rng.uniform(0.10, 0.20)), 0)
                    leads = max(int(cliques_link * rng.uniform(0.01, 0.03)), 0)
                video_plays = int(impressoes * rng.uniform(0.35, 0.55)) if plataforma == "Meta Ads" else 0
                linhas.append({
                    "dia": d, "plataforma": plataforma, "conta": conta,
                    "campanha_id": f"demo-{c_nome[:10]}", "campanha": c_nome,
                    "conjunto": conjunto, "anuncio_id": f"demo-ad-{c_nome[:6]}-{a_idx}",
                    "anuncio": a_nome, "objetivo": obj,
                    "spend": spend, "impressoes": impressoes, "alcance": alcance,
                    "cliques": cliques, "cliques_link": cliques_link,
                    "leads": leads, "mensagens": mensagens, "video_plays": video_plays,
                    "fonte": "demo",
                })
    return pd.DataFrame(linhas)[_COLS_ADS]


# ── Custos de marketing (CAC real) ───────────────────────────────────

_COLS_CUSTOS = ["id", "categoria", "item", "valor_mensal", "mes_inicio", "mes_fim", "ativo", "obs"]
CATEGORIAS_CUSTO = ["Plataforma/CRM", "Portais", "Ferramentas/Apps"]


def carregar_custos() -> pd.DataFrame | None:
    """None = tabela não criada. DEMO_ADS=1 devolve custos fictícios."""
    if os.getenv("DEMO_ADS") == "1":
        return _custos_demo()
    try:
        linhas = buscar_tabela(
            "custos_marketing",
            select="id,categoria,item,valor_mensal,mes_inicio,mes_fim,ativo,obs",
        )
    except TabelaInexistente:
        return None
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=_COLS_CUSTOS)
    df["valor_mensal"] = pd.to_numeric(df["valor_mensal"], errors="coerce").fillna(0.0)
    df["mes_inicio"] = pd.to_datetime(df["mes_inicio"], errors="coerce").dt.date
    df["mes_fim"] = pd.to_datetime(df["mes_fim"], errors="coerce").dt.date
    df["ativo"] = df["ativo"].fillna(True).astype(bool)
    return df


def custos_do_mes(df: pd.DataFrame, mes: date) -> pd.DataFrame:
    """Custos aplicáveis a um mês: ativo, mes_inicio<=mês e (mes_fim vazio ou >=mês)."""
    if df is None or df.empty:
        return df
    m1 = mes.replace(day=1)

    def aplica(r):
        if not bool(r.get("ativo", True)):
            return False
        ini = r.get("mes_inicio")
        if ini is None or pd.isna(ini) or ini > m1:
            return False
        fim = r.get("mes_fim")
        if fim is not None and not pd.isna(fim) and fim < m1:
            return False
        return True

    return df[df.apply(aplica, axis=1)]


def _custos_demo() -> pd.DataFrame:
    ini = (hoje_local().replace(day=1) - timedelta(days=200)).replace(day=1)
    itens = [
        ("Plataforma/CRM", "Jetimob", 890.0),
        ("Portais", "ZAP Imóveis", 1200.0),
        ("Portais", "VivaReal", 800.0),
        ("Portais", "OLX Pro", 350.0),
        ("Ferramentas/Apps", "n8n (servidor)", 120.0),
        ("Ferramentas/Apps", "Z-API (WhatsApp)", 99.0),
        ("Ferramentas/Apps", "IA (OpenAI/Claude)", 150.0),
        ("Ferramentas/Apps", "Brevo (e-mail)", 80.0),
    ]
    linhas = [
        {"id": i + 1, "categoria": c, "item": it, "valor_mensal": v,
         "mes_inicio": ini, "mes_fim": None, "ativo": True, "obs": "demo"}
        for i, (c, it, v) in enumerate(itens)
    ]
    return pd.DataFrame(linhas)[_COLS_CUSTOS]


def carregar_funil() -> tuple[pd.DataFrame, pd.Timestamp] | None:
    """Último snapshot do kanban. None = tabela ausente ou nunca sincronizada."""
    try:
        linhas = buscar_tabela(
            "funil_snapshot",
            select="snapshot_em,contrato,etapa,posicao_etapa,qtd,valor_total",
        )
    except TabelaInexistente:
        return None
    df = pd.DataFrame(linhas)
    if df.empty:
        return None
    df["snapshot_em"] = pd.to_datetime(df["snapshot_em"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    ultimo = df["snapshot_em"].max()
    df = df[df["snapshot_em"] == ultimo].copy()
    df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce").fillna(0)
    return df.sort_values("posicao_etapa"), ultimo


# ── Recortes ─────────────────────────────────────────────────────────

def filtrar_periodo(df: pd.DataFrame, col: str, ini: date, fim: date) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    m = (df[col] >= ini) & (df[col] <= fim)
    return df[m]


def filtrar_canais(df: pd.DataFrame, canais: list[str]) -> pd.DataFrame:
    if df is None or df.empty or not canais:
        return df
    return df[df["canal"].isin(canais)]
