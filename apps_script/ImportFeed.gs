/**
 * ImportFeed.gs - merges data/prices.csv (built twice a day by GitHub Actions) into the Master tab
 * following the benchmark registry: ONE designated benchmark per commodity.
 *
 * prices.csv column `mode`:
 *   feed   - the designated benchmark is an automated source: its price is written to G-P.
 *   manual - the designated benchmark is a manually researched source (refreshed by the scheduled task):
 *            the sheet price is kept, the feed price is written only as the check price.
 *
 * Master columns written: G-P (unit..previous price), R (last update), T ([QA: ...] note),
 * U benchmark product, V designated source, W tier, X check source, Y check price, AA source key.
 * Formula columns A, C, F, Q, S, Z are never written.
 *
 * Setup: Extensions > Apps Script, add this file, run setupFeedTriggers() once and approve.
 */
var FEED_URL = 'https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/prices.csv';
var FEED_LOG_URL = 'https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/run_log.json';
var KEY_OF_SOURCE = {
  'CME/NYMEX/COMEX/ICE futures (Yahoo Finance)': 'yahoo', 'LME official cash settlement (via Westmetall)': 'westmetall',
  'Exchange futures (ICE/Bursa/OSE via Eastmoney)': 'em_global', 'Exchange benchmark of the same good (converted)': 'derived',
  'European Commission Agri-food Data Portal': 'eu_agri', 'Statistics Norway (SSB)': 'ssb',
  'DTN Retail Fertilizer Trends': 'dtn', 'Institute for Rare Earths and Metals (via ScrapMonster)': 'scrapmonster',
  'Strategic Metals Invest': 'smi', '100ppi China spot (ex-VAT)': 'cn_spot', 'Eurostat Comext (EU import unit value)': 'comext',
  'US Census (US import unit value)': 'census', 'UN Comtrade (import unit value)': 'comtrade'
};

function setupFeedTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'importFeed') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('importFeed').timeBased().atHour(8).nearMinute(5).everyDays(1).inTimezone('Asia/Jerusalem').create();
  ScriptApp.newTrigger('importFeed').timeBased().atHour(23).nearMinute(35).everyDays(1).inTimezone('Asia/Jerusalem').create();
}

function importFeed() {
  var ss = SpreadsheetApp.getActive();
  var master = ss.getSheetByName('Master');
  var tz = 'Asia/Jerusalem';
  var now = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm');
  var resp = UrlFetchApp.fetch(FEED_URL + '?t=' + Date.now(), {muteHttpExceptions: true});
  if (resp.getResponseCode() !== 200) { logFeed_(ss, now, 'ERROR', 'HTTP ' + resp.getResponseCode(), 0); return; }
  var rows = Utilities.parseCsv(resp.getContentText('UTF-8'));
  var head = rows.shift(); var c = {};
  head.forEach(function (h, i) { c[h] = i; });

  var n = 2000;
  var gp = master.getRange(2, 7, n, 10).getValues();    // G..P
  var rr = master.getRange(2, 18, n, 1).getValues();    // R
  var tt = master.getRange(2, 20, n, 1).getValues();    // T
  var uy = master.getRange(2, 21, n, 5).getValues();    // U..Y
  var aa = master.getRange(2, 27, n, 1).getValues();    // AA
  var ids = master.getRange(2, 1, n, 5).getValues();
  var hist = []; var priced = 0;

  rows.forEach(function (r) {
    var i = parseInt(r[c.row], 10) - 2;
    if (isNaN(i) || i < 0 || i >= n) return;
    var mode = r[c.mode] || 'feed';
    var key = KEY_OF_SOURCE[r[c.designated_source]] || r[c.source_key];
    var unit = gp[i][0];
    var chk = r[c.check_price] === '' ? '' : parseFloat(r[c.check_price]);
    if (mode === 'manual') {
      // keep the manual benchmark price; refresh only the check columns
      uy[i][3] = r[c.check_source] || '';
      uy[i][4] = (chk !== '' && String(r[c.unit_usd]) === String(unit)) ? chk : '';
      return;
    }
    var price = parseFloat(r[c.price_usd]);
    if (!(price > 0)) return;
    var sameUnit = String(unit) === String(r[c.unit_usd]);
    var prev = (gp[i][2] === '' || gp[i][2] === null) ? gp[i][9] : (sameUnit ? gp[i][2] : '');
    var changed = String(gp[i][2]) !== String(price) || String(gp[i][5]) !== String(r[c.price_date]);
    gp[i] = [r[c.unit_usd], r[c.price_type], price, parseFloat(r[c.orig_price]) || r[c.orig_price], r[c.orig_ccy],
             r[c.price_date], r[c.source], r[c.link], r[c.calc], changed ? prev : gp[i][9]];
    rr[i] = [now];
    var note = String(tt[i][0] || '').replace(/\s*\[QA:[^\]]*\]/g, '');
    var q = r[c.quality];
    tt[i] = [q && q !== 'OK' ? (note + ' [QA: ' + q + ']').trim() : note];
    uy[i] = [r[c.benchmark_product] || uy[i][0], r[c.designated_source] || uy[i][1], r[c.tier] || uy[i][2],
             r[c.check_source] || '', chk];
    aa[i] = [key];
    if (changed) {
      hist.push([now, ids[i][0], ids[i][4], price, r[c.orig_price], r[c.orig_ccy], r[c.price_date], r[c.source]]);
      priced++;
    }
  });

  master.getRange(2, 7, n, 10).setValues(gp);
  master.getRange(2, 18, n, 1).setValues(rr);
  master.getRange(2, 20, n, 1).setValues(tt);
  master.getRange(2, 21, n, 5).setValues(uy);
  master.getRange(2, 27, n, 1).setValues(aa);
  if (hist.length) {
    var h = ss.getSheetByName('History');
    h.getRange(h.getLastRow() + 1, 1, hist.length, hist[0].length).setValues(hist);
  }
  var info = '';
  try {
    var lj = JSON.parse(UrlFetchApp.fetch(FEED_LOG_URL + '?t=' + Date.now()).getContentText());
    info = 'feed run ' + lj.finished_utc + 'Z, ' + lj.rows_with_price + ' rows';
  } catch (e) { info = 'feed log unavailable'; }
  logFeed_(ss, now, 'OK', info, priced);
}

function logFeed_(ss, now, status, msg, n) {
  ss.getSheetByName('Log').appendRow([now, 'GitHub feed import (benchmark model)', msg, n + ' prices changed', status]);
}
