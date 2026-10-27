/**
 * ImportFeed.gs - pulls data/prices.csv from the commodity-feeder GitHub repo
 * (produced twice a day by GitHub Actions) and merges it into the Master tab.
 *
 * Merge rule per row: write the feed price if the cell is empty, or if the feed
 * price date is newer than the date already in the sheet (column L).
 * Columns written: G-O (unit..calculation), P (previous price), R (last update),
 * T (notes: a [QA: ...] tag when the feed flags a price for checking).
 * ARRAYFORMULA columns A, C, F, Q, S are never touched.
 *
 * Setup: paste this file into Extensions > Apps Script (next to CommodityUpdater.gs),
 * run setupFeedTriggers() once and approve the permissions.
 */
var FEED_URL = 'https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/prices.csv';
var FEED_LOG_URL = 'https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/run_log.json';
var HEALTH_URL = 'https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/source_health.csv';

function setupFeedTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'importFeed') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('importFeed').timeBased().atHour(8).nearMinute(5).everyDays(1)
    .inTimezone('Asia/Jerusalem').create();
  ScriptApp.newTrigger('importFeed').timeBased().atHour(23).nearMinute(35).everyDays(1)
    .inTimezone('Asia/Jerusalem').create();
}

function importFeed() {
  var ss = SpreadsheetApp.getActive();
  var master = ss.getSheetByName('Master');
  var tz = 'Asia/Jerusalem';
  var now = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm');

  var resp = UrlFetchApp.fetch(FEED_URL + '?t=' + Date.now(), {muteHttpExceptions: true});
  if (resp.getResponseCode() !== 200) {
    logFeed_(ss, now, 'ERROR', 'HTTP ' + resp.getResponseCode() + ' fetching feed', 0);
    return;
  }
  var rows = Utilities.parseCsv(resp.getContentText('UTF-8'));
  var head = rows.shift();
  var col = {};
  head.forEach(function (h, i) { col[h] = i; });

  var n = 2000;
  var block = master.getRange(2, 7, n, 10).getValues();   // G..P
  var rcol = master.getRange(2, 18, n, 1).getValues();    // R
  var tcol = master.getRange(2, 20, n, 1).getValues();    // T notes
  var ids = master.getRange(2, 1, n, 5).getValues();      // A..E for History
  var hist = [];
  var changed = 0;

  rows.forEach(function (r) {
    var sheetRow = parseInt(r[col.row], 10);
    var i = sheetRow - 2;
    if (isNaN(i) || i < 0 || i >= n) return;
    var price = parseFloat(r[col.price_usd]);
    if (!(price > 0)) return;
    var cur = block[i];
    var curPrice = cur[2];
    var curDate = cur[5] instanceof Date ? Utilities.formatDate(cur[5], tz, 'yyyy-MM-dd') : String(cur[5] || '');
    var newDate = r[col.price_date];
    if (curPrice !== '' && curPrice !== null && curDate && newDate <= curDate) return;
    // China domestic spot (VAT-incl.) and monthly trade unit values do not displace a price
    // that is at most 7 days older: that one is usually an international benchmark.
    var weak = ['cn_spot', 'census', 'comext', 'comtrade'].indexOf(r[col.source_key]) >= 0;
    if (weak && curPrice !== '' && curDate &&
        (new Date(newDate) - new Date(curDate)) / 86400000 <= 7) return;
    var sameUnit = String(cur[0]) === String(r[col.unit_usd]);
    var prev = (curPrice === '' || curPrice === null) ? cur[9] : (sameUnit ? curPrice : '');
    block[i] = [r[col.unit_usd], r[col.price_type], price, parseFloat(r[col.orig_price]) || r[col.orig_price],
                r[col.orig_ccy], newDate, r[col.source], r[col.link], r[col.calc], prev];
    rcol[i] = [now];
    var q = col.quality !== undefined ? r[col.quality] : 'OK';
    var note = String(tcol[i][0] || '').replace(/\s*\[QA:[^\]]*\]/g, '');
    tcol[i] = [q && q !== 'OK' ? (note + ' [QA: ' + q + ']').trim() : note];
    hist.push([now, ids[i][0], ids[i][4], price, r[col.orig_price], r[col.orig_ccy], newDate, r[col.source]]);
    changed++;
  });

  if (changed) {
    master.getRange(2, 7, n, 10).setValues(block);
    master.getRange(2, 18, n, 1).setValues(rcol);
    master.getRange(2, 20, n, 1).setValues(tcol);
    var h = ss.getSheetByName('History');
    h.getRange(h.getLastRow() + 1, 1, hist.length, hist[0].length).setValues(hist);
  }
  var info = '';
  try {
    var lj = JSON.parse(UrlFetchApp.fetch(FEED_LOG_URL + '?t=' + Date.now()).getContentText());
    info = 'feed run ' + lj.finished_utc + 'Z, ' + lj.rows_with_price + ' rows in feed';
  } catch (e) { info = 'feed log unavailable'; }
  logFeed_(ss, now, 'OK', info, changed);
  importHealth_(ss);
}

/** Copies data/source_health.csv into the Source_Health tab (created on first run). */
function importHealth_(ss) {
  try {
    var resp = UrlFetchApp.fetch(HEALTH_URL + '?t=' + Date.now(), {muteHttpExceptions: true});
    if (resp.getResponseCode() !== 200) return;
    var data = Utilities.parseCsv(resp.getContentText('UTF-8'));
    var sh = ss.getSheetByName('Source_Health') || ss.insertSheet('Source_Health');
    sh.clearContents();
    sh.getRange(1, 1, data.length, data[0].length).setValues(data);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, data[0].length).setFontWeight('bold');
  } catch (e) { /* health tab is informational only */ }
}

function logFeed_(ss, now, status, msg, n) {
  var lg = ss.getSheetByName('Log');
  lg.appendRow([now, 'GitHub feed import', msg, n + ' rows updated', status]);
}
