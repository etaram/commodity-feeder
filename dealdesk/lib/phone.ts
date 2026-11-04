// Phones in international form (+<country code><number>) so WhatsApp, call and WeChat buttons work in one click.
// Mirrors leads/contacts.py: a local number gets the company's country calling code; an invalid one is dropped.
export const CC: Record<string, string> = {"AFG":"93","ALB":"355","DZA":"213","AND":"376","AGO":"244","ARG":"54","ARM":"374","AUS":"61","AUT":"43","AZE":"994","BHR":"973","BGD":"880","BLR":"375","BEL":"32","BLZ":"501","BEN":"229","BTN":"975","BOL":"591","BIH":"387","BWA":"267","BRA":"55","BRN":"673","BGR":"359","BFA":"226","BDI":"257","KHM":"855","CMR":"237","CAN":"1","CPV":"238","CAF":"236","TCD":"235","CHL":"56","CHN":"86","COL":"57","COM":"269","COG":"242","COD":"243","CRI":"506","CIV":"225","HRV":"385","CUB":"53","CYP":"357","CZE":"420","DNK":"45","DJI":"253","DOM":"1","ECU":"593","EGY":"20","SLV":"503","GNQ":"240","ERI":"291","EST":"372","SWZ":"268","ETH":"251","FJI":"679","FIN":"358","FRA":"33","GAB":"241","GMB":"220","GEO":"995","DEU":"49","GHA":"233","GRC":"30","GTM":"502","GIN":"224","GNB":"245","GUY":"592","HTI":"509","HND":"504","HKG":"852","HUN":"36","ISL":"354","IND":"91","IDN":"62","IRN":"98","IRQ":"964","IRL":"353","ISR":"972","ITA":"39","JAM":"1","JPN":"81","JOR":"962","KAZ":"7","KEN":"254","KOR":"82","KWT":"965","KGZ":"996","LAO":"856","LVA":"371","LBN":"961","LSO":"266","LBR":"231","LBY":"218","LIE":"423","LTU":"370","LUX":"352","MAC":"853","MDG":"261","MWI":"265","MYS":"60","MDV":"960","MLI":"223","MLT":"356","MRT":"222","MUS":"230","MEX":"52","MDA":"373","MCO":"377","MNG":"976","MNE":"382","MAR":"212","MOZ":"258","MMR":"95","NAM":"264","NPL":"977","NLD":"31","NZL":"64","NIC":"505","NER":"227","NGA":"234","MKD":"389","NOR":"47","OMN":"968","PAK":"92","PAN":"507","PNG":"675","PRY":"595","PER":"51","PHL":"63","POL":"48","PRT":"351","QAT":"974","ROU":"40","RUS":"7","RWA":"250","SAU":"966","SEN":"221","SRB":"381","SYC":"248","SLE":"232","SGP":"65","SVK":"421","SVN":"386","SOM":"252","ZAF":"27","SSD":"211","ESP":"34","LKA":"94","SDN":"249","SUR":"597","SWE":"46","CHE":"41","SYR":"963","TWN":"886","TJK":"992","TZA":"255","THA":"66","TGO":"228","TTO":"1","TUN":"216","TUR":"90","TKM":"993","UGA":"256","UKR":"380","ARE":"971","GBR":"44","USA":"1","URY":"598","UZB":"998","VEN":"58","VNM":"84","YEM":"967","ZMB":"260","ZWE":"263","PSE":"970","XKX":"383","TLS":"670","SLB":"677","VUT":"678","WSM":"685","TON":"676","BHS":"1","BRB":"1","PRI":"1","SMR":"378","GRL":"299","FRO":"298","REU":"262","NCL":"687"};

export function intlPhone(p: string, iso3: string): string {
  let raw = String(p || "").trim();
  if (!raw) return "";
  raw = raw.replace(/\s*(?:ext\.?|x|#)\s*\d+$/i, "");
  let d = raw.replace(/\D/g, "");
  const cc = CC[String(iso3 || "").toUpperCase()] || "";
  if (raw.startsWith("+")) { /* already international */ }
  else if (d.startsWith("00")) d = d.slice(2);
  else if (cc && d.startsWith(cc) && d.length - cc.length >= 7 && !(cc === "1" && d.length === 10)) { /* international without the plus */ }
  else if (cc) d = cc + (d.startsWith("0") && cc !== "39" ? d.slice(1) : d);
  else return raw.startsWith("+") ? raw : "";
  if (d.length < 8 || d.length > 15 || new Set(d.slice(-7)).size === 1) return "";
  return "+" + d;
}

export function cleanPhones(v: string, iso3: string): string {
  const out: string[] = [];
  for (const part of String(v || "").split(/[;,/|]|\s{2,}|\bor\b/)) { const p = intlPhone(part, iso3); if (p && !out.includes(p)) out.push(p); }
  return out.slice(0, 2).join("; ");
}
