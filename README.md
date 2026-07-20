# 📊 Dashboard Tráfego Pago — NL Imóveis

Dashboard de tráfego pago para o mercado imobiliário: conecta o investimento
em mídia (topo de funil) com leads do Jetimob e negócios fechados (fundo de
funil). Feito em **Streamlit + Supabase**, hospedado no **Streamlit Community
Cloud** (share.streamlit.io).

## As 3 visões

| Aba | Para quem | O que mostra |
|---|---|---|
| 📈 **Visão Geral** | Gestor (dia a dia) | Investimento, impressões, CTR, CPC, leads/dia, CPL, canais, origens, bairros |
| 🔀 **Funil → Vendas** | Tráfego + Comercial | Fluxo lead→fechamento, CAC, ROAS, custo por VGV, kanban por etapa, conversão por canal, ranking de corretores |
| 🏛️ **Executivo** | Diretoria | Mês × mês anterior, VGV oficial, custo por VGV, imóveis/bairros mais procurados, aproveitamento por corretor |

## Arquitetura

```
Jetimob ─ webhook ─→ n8n ─→ Supabase.leads_jetimob        (tempo real)
Jetimob ─ scraping (cron 10h/15h) ─→ Supabase.vendas_nl   (fechamentos)
Jetimob ─ sync_funil_jetimob.py ─→ Supabase.funil_snapshot (kanban por etapa)
Meta Ads ─ sync_meta_ads.py ─→ Supabase.ads_insights_daily (investimento)
                                        │
                                        ▼
                          Streamlit Cloud (este app)
```

Fuso horário: America/Fortaleza. Cache de dados: 10 min (botão "Atualizar
dados" força recarga).

## Mapa de canais

A coluna `origem` do lead vira **canal** assim (ver `utils/dados.py`):

- **Portais** — ZAP, VivaReal, OLX, Chaves na Mão, Imovelweb…
- **Site NL** — origem contendo "site"
- **Meta Ads** — Facebook / Instagram / Meta
- **Google Ads** — Google / YouTube / PMax
- **Direto/Outros** — WhatsApp, App Jetimob, indicação, telefone, sem origem

> ⚠️ Enquanto a integração Facebook↔Jetimob não for reconectada, leads de
> formulário do Meta podem entrar sem origem — o card "Leads pagos no CRM"
> da Visão Geral existe justamente pra monitorar esse gap.

---

## Como rodar localmente

```bash
cd ~/Documents/Claude/Dashboard_Trafego_Pago_NL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

O `.streamlit/secrets.toml` local já tem as credenciais (não versionado).

## Ativar o schema novo no Supabase (1x)

1. Abrir [supabase.com](https://supabase.com) → projeto → **SQL Editor**
2. Colar o conteúdo de `sql/01_trafego_pago_schema.sql` → **Run**
3. Pronto: cria `ads_insights_daily` e `funil_snapshot` (com RLS fechada)

O dashboard funciona sem esse passo — as seções de investimento e kanban
apenas mostram um aviso até as tabelas existirem.

---

## 🚀 Deploy no share.streamlit.io (passo a passo)

### 1. Subir para o GitHub

```bash
cd ~/Documents/Claude/Dashboard_Trafego_Pago_NL
git init && git add -A && git commit -m "Dashboard Tráfego Pago NL"
```

Criar repo **privado** `dashboard-trafego-nl` na conta
[github.com/nladmmarketing-sudo](https://github.com/nladmmarketing-sudo)
(mesma do nl-imoveis-crm) e:

```bash
git remote add origin https://github.com/nladmmarketing-sudo/dashboard-trafego-nl.git
git branch -M main && git push -u origin main
```

### 2. Criar o app no Streamlit Cloud

1. Acessar [share.streamlit.io](https://share.streamlit.io) → login com o GitHub `nladmmarketing-sudo`
2. **Create app** → *Deploy a public app from GitHub*
3. Repository: `nladmmarketing-sudo/dashboard-trafego-nl` · Branch: `main` · Main file: `app.py`
4. Em **Advanced settings → Secrets**, colar o conteúdo do seu
   `.streamlit/secrets.toml` local (Supabase + senha + Meta)
5. **Deploy** — a URL fica tipo `https://dashboard-trafego-nl.streamlit.app`

> A senha de acesso do painel é a de `[app] senha` nos Secrets.
> **Troque a senha padrão antes de divulgar o link** (o painel expõe VGV
> e nomes de clientes — LGPD).

### 3. Atualizações

Todo `git push` na `main` redeploya sozinho. Secrets são editáveis em
App → Settings → Secrets (sem novo push).

---

## Syncs (rodam no Mac, não no Streamlit Cloud)

### Investimento Meta Ads

```bash
# backfill de 90 dias (1ª vez)
python3 sync/sync_meta_ads.py --desde 2026-04-22

# diário (cron às 9h, junto dos syncs existentes)
0 9 * * * cd ~/Documents/Claude/Dashboard_Trafego_Pago_NL && /usr/bin/python3 sync/sync_meta_ads.py >> /tmp/sync_meta_ads.log 2>&1
```

Precisa de token com escopo `ads_read` em `[meta] token` no secrets.toml
local. Token do Graph Explorer dura ~24h; para cron, trocar por long-lived
(~60 dias):

```
https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=1323987856315261&client_secret=SEGREDO_DO_APP&fb_exchange_token=TOKEN_CURTO
```

Sem token, dá pra **lançar investimento manual** direto na aba Executivo.

### Fotografia do kanban (funil por etapa)

```bash
# usa a mesma sessão do sync de vendas (~/.jetimob-browser-profile)
python3 sync/sync_funil_jetimob.py

# sugestão de cron (10h05, logo após o sync de vendas)
5 10 * * * cd ~/Documents/Claude/Dashboard_Trafego_Pago_NL && "$HOME/Agencia/06-clientes/nl-imoveis/01-dashboard-jetimob/streamlit-app-DELETAR-DEPOIS/.venv/bin/python" sync/sync_funil_jetimob.py >> /tmp/sync_funil.log 2>&1
```

Se a sessão do Jetimob expirar (o log avisa):

```bash
python3 ~/Agencia/06-clientes/nl-imoveis/01-dashboard-jetimob/scripts/login_jetimob.py
```

---

## Segurança & LGPD

- Painel atrás de **senha única** (secrets) — trocar a padrão antes de divulgar
- Nome de cliente aparece **abreviado** (ex.: "Maria S."); telefone nunca aparece
- Tabelas novas com **RLS fechada** (anon key não lê nada)
- Service key vive só nos Secrets (server-side) e no secrets.toml local
  (gitignored) — **nunca** commitar

## Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| "Investimento ainda não conectado" | schema não aplicado | rodar `sql/01_trafego_pago_schema.sql` |
| "Sem dados de investimento no período" | sync nunca rodou / token vazio | rodar `sync_meta_ads.py` ou lançar manual |
| Kanban vazio na aba Funil | snapshot nunca rodou | rodar `sync_funil_jetimob.py` |
| "Sessão expirada" nos syncs | login do Jetimob caiu | rodar `login_jetimob.py` e repetir |
| Vendas desatualizadas | cron 10h/15h falhou | checar `~/Agencia/.../logs/sync_vendas_nl.log` |
