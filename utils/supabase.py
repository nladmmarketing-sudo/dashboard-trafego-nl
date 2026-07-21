"""Cliente REST do Supabase — paginação além do limite de 1000 linhas
do PostgREST e detecção de tabela inexistente (schema ainda não aplicado).
"""

import requests
import streamlit as st


class TabelaInexistente(Exception):
    """A tabela ainda não foi criada no Supabase (rodar sql/01_trafego_pago_schema.sql)."""


def _credenciais() -> tuple[str, str]:
    try:
        cfg = st.secrets["supabase"]
        return cfg["url"].rstrip("/"), cfg["key"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Credenciais do Supabase não configuradas. Crie `.streamlit/secrets.toml` "
            "a partir do `secrets.example.toml` (local) ou preencha os Secrets no "
            "Streamlit Cloud (Settings → Secrets)."
        )
        st.stop()


def _headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


@st.cache_data(ttl=600, show_spinner=False)
def buscar_tabela(tabela: str, select: str = "*", filtros: str = "", page_size: int = 1000) -> list[dict]:
    """Busca todas as linhas de uma tabela/view, paginando de 1000 em 1000.

    `filtros` é a query string extra do PostgREST, ex.: "dia=gte.2026-01-01".
    """
    url_base, key = _credenciais()
    url = f"{url_base}/rest/v1/{tabela}?select={select}"
    if filtros:
        url += f"&{filtros}"

    linhas: list[dict] = []
    offset = 0
    while True:
        headers = _headers(key)
        headers["Range"] = f"{offset}-{offset + page_size - 1}"
        headers["Prefer"] = "count=exact"
        resp = requests.get(url, headers=headers, timeout=30)

        if resp.status_code == 404 or (
            resp.status_code == 400 and "42P01" in resp.text
        ):
            raise TabelaInexistente(tabela)
        resp.raise_for_status()

        lote = resp.json()
        linhas.extend(lote)

        # content-range: "0-999/11153" — para quando trouxe tudo
        total = None
        cr = resp.headers.get("content-range", "")
        if "/" in cr and cr.split("/")[-1].isdigit():
            total = int(cr.split("/")[-1])

        if len(lote) < page_size or (total is not None and len(linhas) >= total):
            return linhas
        offset += page_size


def inserir(tabela: str, linhas: list[dict], on_conflict: str = "") -> None:
    """Insere/upserta linhas (usado pelo lançamento manual de investimento)."""
    url_base, key = _credenciais()
    url = f"{url_base}/rest/v1/{tabela}"
    headers = _headers(key)
    headers["Content-Type"] = "application/json"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    else:
        headers["Prefer"] = "return=minimal"
    resp = requests.post(url, headers=headers, json=linhas, timeout=30)
    if resp.status_code == 404 or (resp.status_code == 400 and "42P01" in resp.text):
        raise TabelaInexistente(tabela)
    resp.raise_for_status()


def atualizar(tabela: str, id_val, campos: dict) -> None:
    """PATCH de uma linha por id."""
    url_base, key = _credenciais()
    url = f"{url_base}/rest/v1/{tabela}?id=eq.{id_val}"
    headers = _headers(key)
    headers["Content-Type"] = "application/json"
    headers["Prefer"] = "return=minimal"
    resp = requests.patch(url, headers=headers, json=campos, timeout=30)
    resp.raise_for_status()


def deletar(tabela: str, id_val) -> None:
    """DELETE de uma linha por id."""
    url_base, key = _credenciais()
    url = f"{url_base}/rest/v1/{tabela}?id=eq.{id_val}"
    headers = _headers(key)
    headers["Prefer"] = "return=minimal"
    resp = requests.delete(url, headers=headers, timeout=30)
    resp.raise_for_status()
