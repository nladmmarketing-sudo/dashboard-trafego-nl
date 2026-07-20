#!/usr/bin/env python3
"""sync_funil_jetimob.py — Fotografia do kanban do Jetimob → Supabase (funil_snapshot).

Conta as oportunidades ABERTAS por etapa (venda/locação/temporada) e grava
uma linha por etapa com timestamp. O dashboard mostra sempre a fotografia
mais recente na aba "Funil → Vendas".

Reusa o profile Playwright já logado do sync de vendas:
  ~/.jetimob-browser-profile
Se a sessão expirou, rode antes:
  python3 ~/Agencia/06-clientes/nl-imoveis/01-dashboard-jetimob/scripts/login_jetimob.py

Uso:
  python3 sync_funil_jetimob.py [--dry-run]

Dependências (não precisam estar no requirements.txt do app):
  pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://app.jetimob.com"
USER_DATA_DIR = Path.home() / ".jetimob-browser-profile"
CONTRATOS = {1: "venda", 2: "locacao", 3: "temporada"}


def carregar_supabase() -> tuple[str, str]:
    secrets = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not secrets.exists():
        sys.exit("❌ .streamlit/secrets.toml não encontrado (seção [supabase]).")
    data = tomllib.loads(secrets.read_text())
    sb = data.get("supabase", {})
    if not sb.get("url") or not sb.get("key"):
        sys.exit("❌ [supabase] url/key ausentes no secrets.toml.")
    return sb["url"].rstrip("/"), sb["key"]


def assert_logged_in(page) -> None:
    try:
        ok = page.evaluate("""async () => {
            const r = await fetch('/api/check', { credentials: 'include' });
            return r.ok;
        }""")
    except Exception:
        ok = False
    if not ok or "login" in page.url.lower():
        sys.exit(
            "\n❌ Sessão do Jetimob expirada. Rode primeiro:\n"
            "   python3 ~/Agencia/06-clientes/nl-imoveis/01-dashboard-jetimob/scripts/login_jetimob.py\n"
        )


def fetch_json(page, url: str) -> dict | None:
    return page.evaluate(
        """async (u) => {
            const r = await fetch(u, { credentials: 'include',
                                       headers: { 'Accept': 'application/json' } });
            if (!r.ok) return null;
            return await r.json();
        }""",
        url,
    )


def fetch_funnels(page) -> dict[str, int]:
    """contrato → funnel_id (a API exige funnel_id desde ~jun/2026)."""
    payload = fetch_json(
        page, f"{BASE_URL}/api/oportunidades/kanban?busca=&funnel_id=&status=&page=1"
    )
    funnels = (payload or {}).get("data", {}).get("funnels", [])
    mapa = {}
    for f in funnels:
        nome = CONTRATOS.get(f.get("contract_id"))
        if nome:
            mapa[nome] = f["id"]
    return mapa


def snapshot_contrato(page, contrato: str, funnel_id: int) -> list[dict]:
    """Percorre todas as páginas do kanban (status aberto) somando por etapa."""
    etapas: dict[str, dict] = {}
    ordem: list[str] = []
    pg = 1
    while True:
        url = (
            f"{BASE_URL}/api/oportunidades/kanban"
            f"?busca=&funnel_id={funnel_id}&contrato={contrato}&responsavel=&status="
            f"&atualizacao=&etapa=&temperatura=&fonte_prospeccao=&portal="
            f"&rede_social=&createdDate=&updatedDate=&agendamento=&labels="
            f"&headquarter=&page={pg}"
        )
        payload = fetch_json(page, url)
        if not payload or "data" not in payload:
            break
        data = payload["data"]
        opps = data.get("opportunities", [])
        if isinstance(opps, dict):
            opps = list(opps.values())

        itens_pagina = 0
        for etapa in opps:
            nome = etapa.get("name", "(sem etapa)")
            if nome not in etapas:
                etapas[nome] = {"qtd": 0, "valor": 0.0}
                ordem.append(nome)
            items = etapa.get("items") or []
            if isinstance(items, dict):
                items = list(items.values())
            for it in items:
                etapas[nome]["qtd"] += 1
                bruto = int(it.get("maxValue") or 0)
                etapas[nome]["valor"] += round(bruto / 100, 2) if bruto >= 100 else float(bruto)
                itens_pagina += 1

        total_api = data.get("total_items", 0)
        soma = sum(e["qtd"] for e in etapas.values())
        print(f"    pág {pg}: +{itens_pagina} (acum. {soma}/{total_api})")
        if not itens_pagina or soma >= total_api:
            break
        pg += 1

    return [
        {"contrato": contrato, "etapa": nome, "posicao_etapa": i,
         "qtd": etapas[nome]["qtd"], "valor_total": round(etapas[nome]["valor"], 2)}
        for i, nome in enumerate(ordem)
    ]


def inserir_supabase(sb_url: str, sb_key: str, linhas: list[dict]) -> None:
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/funil_snapshot",
        data=json.dumps(linhas).encode(),
        method="POST",
        headers={
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()[:300]
        if e.code == 404 or "42P01" in corpo:
            sys.exit(
                "❌ Tabela funil_snapshot não existe.\n"
                "   Rode sql/01_trafego_pago_schema.sql no SQL Editor do Supabase."
            )
        sys.exit(f"❌ Erro no Supabase: {e.code} — {corpo}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not USER_DATA_DIR.exists():
        sys.exit("❌ Profile do Jetimob não encontrado. Rode login_jetimob.py primeiro.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("❌ Playwright não instalado: pip install playwright && python -m playwright install chromium")

    sb_url, sb_key = carregar_supabase()
    agora = datetime.now(timezone.utc).isoformat()
    linhas: list[dict] = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA_DIR), headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = ctx.new_page()
        print("🌐 Verificando sessão no Jetimob…")
        page.goto(f"{BASE_URL}/oportunidades", wait_until="domcontentloaded", timeout=30_000)
        assert_logged_in(page)
        print("   ✅ sessão válida")

        funnels = fetch_funnels(page)
        if not funnels:
            sys.exit("❌ Não consegui mapear os funis (funnel_id). API mudou?")
        print(f"🔀 Funis: {funnels}")

        for contrato, funnel_id in funnels.items():
            print(f"📋 Kanban {contrato}…")
            linhas += [dict(l, snapshot_em=agora) for l in snapshot_contrato(page, contrato, funnel_id)]
        ctx.close()

    print(f"\n📊 {len(linhas)} etapas capturadas")
    for l in linhas:
        print(f"   {l['contrato']:10s} {l['etapa']:30s} {l['qtd']:4d}  R$ {l['valor_total']:>12,.2f}")

    if args.dry_run:
        print("🔍 dry-run: nada gravado.")
        return
    if linhas:
        inserir_supabase(sb_url, sb_key, linhas)
        print("✅ Snapshot gravado em funil_snapshot.")


if __name__ == "__main__":
    main()
