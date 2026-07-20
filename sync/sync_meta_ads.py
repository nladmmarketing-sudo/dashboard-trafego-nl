#!/usr/bin/env python3
"""sync_meta_ads.py — Investimento diário do Meta Ads → Supabase (ads_insights_daily).

Puxa insights por campanha/dia da Graph API (Marketing API) e faz upsert
no Supabase. Rodar 1x/dia (cron) ou manualmente para backfill.

Uso:
  python3 sync_meta_ads.py                     # últimos 7 dias
  python3 sync_meta_ads.py --desde 2026-04-01  # backfill
  python3 sync_meta_ads.py --dry-run

Credenciais (ordem de busca):
  1. Variáveis de ambiente META_TOKEN / META_CONTA / SUPABASE_URL / SUPABASE_KEY
  2. ../.streamlit/secrets.toml (seções [meta] e [supabase])

O token precisa do escopo ads_read (token de usuário do app CLAUDE
AUTOMATIZADO serve). Tokens colados do Graph Explorer duram ~24h; para
rodar em cron, gere um long-lived (~60 dias) — ver README.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

GRAPH = "https://graph.facebook.com/v21.0"


def carregar_config() -> dict:
    cfg = {
        "token": os.getenv("META_TOKEN", ""),
        "conta": os.getenv("META_CONTA", ""),
        "sb_url": os.getenv("SUPABASE_URL", ""),
        "sb_key": os.getenv("SUPABASE_KEY", ""),
    }
    secrets = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if secrets.exists():
        data = tomllib.loads(secrets.read_text())
        cfg["token"] = cfg["token"] or data.get("meta", {}).get("token", "")
        cfg["conta"] = cfg["conta"] or data.get("meta", {}).get("conta", "")
        cfg["sb_url"] = cfg["sb_url"] or data.get("supabase", {}).get("url", "")
        cfg["sb_key"] = cfg["sb_key"] or data.get("supabase", {}).get("key", "")
    faltando = [k for k, v in cfg.items() if not v and k != "token"]
    if faltando:
        sys.exit(f"❌ Configuração faltando: {faltando} (ver docstring)")
    if not cfg["token"]:
        sys.exit(
            "❌ Sem token do Meta.\n"
            "   Cole em [meta] token no .streamlit/secrets.toml ou exporte META_TOKEN.\n"
            "   Gerar: https://developers.facebook.com/tools/explorer (app CLAUDE AUTOMATIZADO, escopo ads_read)"
        )
    return cfg


def http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def extrair_acao(actions: list[dict] | None, *tipos: str) -> int:
    total = 0
    for a in actions or []:
        if a.get("action_type") in tipos:
            total += int(float(a.get("value", 0)))
    return total


def buscar_insights(cfg: dict, desde: date, ate: date) -> list[dict]:
    campos = ("campaign_id,campaign_name,objective,spend,impressions,reach,"
              "clicks,inline_link_clicks,actions")
    params = {
        "level": "campaign",
        "time_increment": 1,
        "fields": campos,
        "time_range": json.dumps({"since": desde.isoformat(), "until": ate.isoformat()}),
        "limit": 500,
        "access_token": cfg["token"],
    }
    url = f"{GRAPH}/{cfg['conta']}/insights?{urllib.parse.urlencode(params)}"

    linhas: list[dict] = []
    while url:
        try:
            payload = http_json(url)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode()[:300]
            if e.code in (400, 401) and "token" in corpo.lower():
                sys.exit(f"❌ Token inválido/expirado. Gere outro (ads_read).\n   {corpo}")
            sys.exit(f"❌ Erro na Graph API: {e.code} — {corpo}")

        for row in payload.get("data", []):
            linhas.append({
                "dia": row["date_start"],
                "plataforma": "Meta Ads",
                "conta": cfg["conta"],
                "campanha_id": row.get("campaign_id", ""),
                "campanha": row.get("campaign_name", ""),
                "objetivo": (row.get("objective") or "").lower(),
                "spend": float(row.get("spend") or 0),
                "impressoes": int(row.get("impressions") or 0),
                "alcance": int(row.get("reach") or 0),
                "cliques": int(row.get("clicks") or 0),
                "cliques_link": int(row.get("inline_link_clicks") or 0),
                "leads": extrair_acao(row.get("actions"), "lead", "onsite_conversion.lead_grouped"),
                "mensagens": extrair_acao(row.get("actions"),
                                          "onsite_conversion.messaging_conversation_started_7d"),
                "fonte": "api",
            })
        url = payload.get("paging", {}).get("next", "")
    return linhas


def upsert_supabase(cfg: dict, linhas: list[dict]) -> None:
    url = (f"{cfg['sb_url'].rstrip('/')}/rest/v1/ads_insights_daily"
           f"?on_conflict=dia,plataforma,campanha_id,fonte")
    req = urllib.request.Request(
        url,
        data=json.dumps(linhas).encode(),
        method="POST",
        headers={
            "apikey": cfg["sb_key"],
            "Authorization": f"Bearer {cfg['sb_key']}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()[:300]
        if e.code == 404 or "42P01" in corpo:
            sys.exit(
                "❌ Tabela ads_insights_daily não existe.\n"
                "   Rode sql/01_trafego_pago_schema.sql no SQL Editor do Supabase e tente de novo."
            )
        sys.exit(f"❌ Erro no Supabase: {e.code} — {corpo}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desde", default=(date.today() - timedelta(days=7)).isoformat())
    parser.add_argument("--ate", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = carregar_config()
    desde, ate = date.fromisoformat(args.desde), date.fromisoformat(args.ate)

    print(f"📥 Meta Ads insights {desde} → {ate} ({cfg['conta']})")
    linhas = buscar_insights(cfg, desde, ate)
    gasto = sum(l["spend"] for l in linhas)
    print(f"   {len(linhas)} linhas campanha×dia · gasto total R$ {gasto:,.2f}")

    if args.dry_run:
        for l in linhas[:8]:
            print(f"   • {l['dia']} {l['campanha'][:40]:40s} R$ {l['spend']:>9.2f} "
                  f"leads={l['leads']} msgs={l['mensagens']}")
        print("🔍 dry-run: nada gravado.")
        return

    if linhas:
        upsert_supabase(cfg, linhas)
        print("✅ Upsert concluído em ads_insights_daily.")
    else:
        print("   Nada a gravar.")


if __name__ == "__main__":
    main()
