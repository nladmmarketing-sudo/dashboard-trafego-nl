-- ============================================================
-- Dashboard Tráfego Pago NL — schema adicional
-- Colar no Supabase: SQL Editor → New query → Run
-- Projeto: ybpicxohafsulmwxbewa
-- Idempotente: pode rodar mais de uma vez sem quebrar nada.
-- ============================================================

-- 1) Investimento e métricas diárias de mídia paga (Meta / Google)
--    Alimentada por sync/sync_meta_ads.py (fonte='api')
--    ou por lançamento manual no próprio dashboard (fonte='manual').
create table if not exists ads_insights_daily (
  id            bigint generated always as identity primary key,
  dia           date        not null,
  plataforma    text        not null,              -- 'Meta Ads' | 'Google Ads'
  conta         text,                              -- ex.: act_476390709618184
  campanha_id   text        not null default '',
  campanha      text,
  conjunto      text,                              -- ad set / grupo de anúncios
  anuncio_id    text        not null default '',   -- chave natural do anúncio ('' se agregado/manual)
  anuncio       text,                              -- nome do anúncio/criativo
  objetivo      text,                              -- leads | mensagens | engajamento...
  spend         numeric(12,2) not null default 0,  -- em BRL
  impressoes    bigint      not null default 0,
  alcance       bigint      not null default 0,
  cliques       bigint      not null default 0,    -- todos os cliques
  cliques_link  bigint      not null default 0,    -- cliques no link
  leads         integer     not null default 0,    -- lead forms / conversões de lead
  mensagens     integer     not null default 0,    -- conversas iniciadas
  video_plays   bigint      not null default 0,    -- reproduções de vídeo
  fonte         text        not null default 'api',-- 'api' | 'manual'
  criado_em     timestamptz not null default now(),
  -- chave natural: 1 linha por anúncio por dia por fonte
  -- (manual usa anuncio_id = 'manual-<dia>' para não colidir)
  unique (dia, plataforma, anuncio_id, fonte)
);

create index if not exists idx_ads_insights_dia on ads_insights_daily (dia);
create index if not exists idx_ads_insights_plataforma on ads_insights_daily (plataforma, dia);

-- Fechada para anon/authenticated (sem policy = ninguém lê com anon key).
-- O dashboard e os syncs usam a service key, que ignora RLS.
alter table ads_insights_daily enable row level security;

comment on table ads_insights_daily is
  'Métricas diárias de mídia paga por anúncio (Meta/Google). Alimentada por sync_meta_ads.py ou lançamento manual.';

-- 2) Snapshot do funil comercial do Jetimob (kanban)
--    Alimentada por sync/sync_funil_jetimob.py — cada execução grava
--    uma "fotografia" da quantidade de oportunidades por etapa.
create table if not exists funil_snapshot (
  id            bigint generated always as identity primary key,
  snapshot_em   timestamptz not null default now(),
  contrato      text        not null,   -- venda | locacao | temporada
  etapa         text        not null,   -- nome da etapa no kanban
  posicao_etapa integer     not null default 0,  -- ordem da coluna no kanban
  qtd           integer     not null default 0,
  valor_total   numeric(14,2) not null default 0 -- soma dos valores das oportunidades (BRL)
);

create index if not exists idx_funil_snapshot_em on funil_snapshot (snapshot_em desc);

alter table funil_snapshot enable row level security;

comment on table funil_snapshot is
  'Fotografias periódicas do kanban de oportunidades do Jetimob, por etapa e tipo de contrato.';
