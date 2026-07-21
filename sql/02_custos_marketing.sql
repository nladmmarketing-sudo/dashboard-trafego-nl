-- ============================================================
-- Dashboard Tráfego Pago NL — custos de marketing (CAC real)
-- Colar no Supabase: SQL Editor → New query → Run
-- Idempotente.
-- ============================================================

-- Custos fixos/recorrentes de marketing (plataformas, portais, ferramentas).
-- A mídia paga (Meta/Google) NÃO entra aqui — vem de ads_insights_daily.
-- Um custo recorrente vale de mes_inicio até mes_fim (null = ainda ativo).
create table if not exists custos_marketing (
  id            bigint generated always as identity primary key,
  categoria     text        not null,   -- 'Plataforma/CRM' | 'Portais' | 'Ferramentas/Apps'
  item          text        not null,   -- 'Jetimob', 'ZAP Imóveis', 'n8n'...
  valor_mensal  numeric(12,2) not null default 0,
  mes_inicio    date        not null,   -- 1º dia do mês em que o custo começou
  mes_fim       date,                    -- null = ainda ativo (conta em todo mês >= mes_inicio)
  ativo         boolean     not null default true,
  obs           text,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  unique (categoria, item, mes_inicio)
);

create index if not exists idx_custos_mkt_inicio on custos_marketing (mes_inicio);

-- Fechada para anon/authenticated (service key ignora RLS).
alter table custos_marketing enable row level security;

comment on table custos_marketing is
  'Custos fixos/recorrentes de marketing (plataforma/CRM, portais, ferramentas). Mídia paga vem de ads_insights_daily. Usado para CAC/ROI real da empresa.';
