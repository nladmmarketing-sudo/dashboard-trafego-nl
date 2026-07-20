"""Camada de dados: carrega tabelas do Supabase, classifica origens em
canais de mídia e resolve janelas de período (fuso America/Fortaleza).

Fontes:
- leads_jetimob        → leads em tempo real (webhook Jetimob → n8n)
- vendas_nl            → negócios fechados (sync diário via kanban Jetimob)
- resumo_mensal_jetimob→ totais oficiais do relatório do Jetimob (vendas)
- ads_insights_daily   → investimento Meta/Google (sync_meta_ads.py ou manual)
- funil_snapshot       → fotografia do kanban por etapa (sync_funil_jetimob.py)
"""

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


def carregar_ads() -> pd.DataFrame | None:
    """None = tabela ainda não criada (schema pendente)."""
    try:
        linhas = buscar_tabela("ads_insights_daily")
    except TabelaInexistente:
        return None
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(
            columns=["dia", "plataforma", "campanha", "objetivo", "spend", "impressoes",
                     "alcance", "cliques", "cliques_link", "leads", "mensagens", "fonte"]
        )
    df["dia"] = pd.to_datetime(df["dia"]).dt.date
    for c in ("spend", "impressoes", "alcance", "cliques", "cliques_link", "leads", "mensagens"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


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
