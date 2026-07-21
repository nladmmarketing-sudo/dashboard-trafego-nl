/**
 * Google Ads Script — NL Imóveis → Supabase (via proxy n8n)
 * ---------------------------------------------------------------
 * INSTALADO e AGENDADO (21/07/2026) na conta 910-516-4143:
 *   Ferramentas → Ações em massa → Scripts → "Sync Google Ads → Supabase"
 *   Frequência: A CADA HORA. Roda na nuvem do Google (não depende do Mac).
 *
 * ARQUITETURA:
 *   Google Ads Script (este) → webhook n8n → Supabase (server-side)
 *   Por que o proxy: a chave secreta do Supabase (sb_secret_) é BLOQUEADA
 *   quando usada de contexto "navegador" (o UrlFetchApp do Ads Script cai
 *   nesse caso — erro 401 "Forbidden use of secret API key in browser").
 *   O n8n grava server-side, onde a chave funciona. Bônus: nenhuma chave
 *   de banco fica exposta aqui — só a URL do webhook.
 *
 *   Workflow n8n: "Google Ads -> Supabase (proxy)" id rQMWM8jbYldn02Nh
 *   Webhook: https://n8n.nlimoveis.com.br/webhook/google-ads-sync
 *
 * Conversões do Google = "leads" (o lance é Maximizar conversões).
 */

var WEBHOOK = 'https://n8n.nlimoveis.com.br/webhook/google-ads-sync';
var CONTA = '910-516-4143';
var LOOKBACK_DIAS = 45;   // re-sincroniza os últimos N dias a cada execução
                          // (pega conversões atribuídas com atraso).

function main() {
  var hoje = new Date();
  var ini = new Date(hoje.getTime() - LOOKBACK_DIAS * 24 * 60 * 60 * 1000);
  var desde = _fmt(ini), ate = _fmt(hoje);

  var query =
    'SELECT campaign.id, campaign.name, segments.date, ' +
    'metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions ' +
    'FROM campaign ' +
    'WHERE segments.date BETWEEN "' + desde + '" AND "' + ate + '" ' +
    'AND metrics.impressions > 0';

  var it = AdsApp.search(query);
  var linhas = [];
  while (it.hasNext()) {
    var r = it.next();
    var c = r.campaign, s = r.segments, m = r.metrics;
    var spend = Number(m.costMicros || 0) / 1000000;
    linhas.push({
      dia: s.date, plataforma: 'Google Ads', conta: CONTA,
      campanha_id: String(c.id), campanha: c.name,
      anuncio_id: 'gads-' + c.id, anuncio: c.name, objetivo: 'leads',
      spend: Math.round(spend * 100) / 100,
      impressoes: Number(m.impressions || 0),
      cliques: Number(m.clicks || 0), cliques_link: Number(m.clicks || 0),
      leads: Math.round(Number(m.conversions || 0)), fonte: 'api'
    });
  }

  if (!linhas.length) { Logger.log('Nenhuma linha no periodo.'); return; }

  var LOTE = 200, gravadas = 0;
  for (var i = 0; i < linhas.length; i += LOTE) {
    var chunk = linhas.slice(i, i + LOTE);
    var resp = UrlFetchApp.fetch(WEBHOOK, {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify(chunk), muteHttpExceptions: true
    });
    var code = resp.getResponseCode();
    if (code >= 200 && code < 300) { gravadas += chunk.length; }
    else { Logger.log('ERRO n8n (' + code + '): ' + resp.getContentText().substring(0, 300)); }
  }
  Logger.log('OK - ' + gravadas + '/' + linhas.length + ' linhas Google Ads (' + desde + ' a ' + ate + ').');
}

function _fmt(d) {
  var mm = ('0' + (d.getMonth() + 1)).slice(-2);
  var dd = ('0' + d.getDate()).slice(-2);
  return d.getFullYear() + '-' + mm + '-' + dd;
}
