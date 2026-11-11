// What a tender buys: goods, no goods (works, services, consulting, a study, a programme), a mix of both, or unknown.
// Rules and word lists only: deterministic, no model call, no I/O. Used behind the flag TENDER_KIND=on by the
// "suppliers for this tender" search (lib/panel.ts tenderPlan) and scored by tools/eval-tenderkind.ts.
//
// How a title is read:
//   1. A structured hint, when the row has one, comes first: the procurement category (the tender column "nature":
//      goods / works / services / consulting) and the CPV division (45 works, 50-98 services, 03-44 and 48 goods).
//   2. The wording. The first cue in the title is its head:
//        a buying cue ("supply of X", "fourniture de X", "adquisición de X", "aquisição de X"): X decides. A service
//          or works noun as X ("supply of consultancy services") buys no goods; goods followed by a service
//          ("supply of equipment and training of staff") is mixed; a purpose clause after X ("for the maintenance
//          of ...") is ignored.
//        a works or service cue ("rehabilitation of", "technical assistance for", "maintenance of"): no goods, unless
//          a supply is added to it ("construction of a clinic and supply of equipment": mixed).
//   3. Nothing decides: "unknown". Goods are never guessed: a goods verdict needs a buying cue, a goods hint, or
//      (low confidence only) a plain goods noun such as "equipment".
// The costly mistake is calling a goods tender "non_goods" with high confidence (the user would get an empty list),
// so a service or works word only counts where it is used as the thing bought, not as a describing word
// ("cleaning materials", "matériaux de construction", "training manuals" stay goods).
//
// All matching runs on a folded copy of the text (lower case, accents removed, same length as the original), so the
// word lists below are written without accents and the positions found can be used on the original title.

export type TenderKindInput = { title: string; sector?: string; description?: string; cpv?: string; category?: string };
export type TenderKind = { kind: "goods" | "non_goods" | "mixed" | "unknown"; confidence: "high" | "low"; why: string; goods_phrases: string[] };

// ---- word lists (regular-expression fragments, matched on the folded text) ----

/** buying verbs: the title names what is bought right after them */
const BUY = ["supply", "supplying", "delivery", "procurement", "procuring", "purchase", "purchasing", "acquisition",   // English
  "fournitures?", "livraison", "achats?", "approvisionnement",                                                             // French (acquisition is shared)
  "adquisicion", "suministros?", "compra", "dotacion", "abastecimiento",                                                   // Spanish
  "aquisicao", "fornecimento"];                                                                                            // Portuguese (compra is shared)
/** weak buying verbs: also used for services ("provision of security guards"), so the object must name goods */
const BUY_WEAK = ["provision", "provisioning", "entrega", "prestacion", "prestacao"];
/** installing: alone ("installation of X") or next to a buying verb ("supply and installation of X") it means mixed */
const INSTALL = ["installation", "installing", "install", "commissioning", "laying", "fixing", "erection", "pose", "mise en service", "mise en place", "montage",
  "instalacion", "montaje", "puesta en marcha", "puesta en servicio", "puesta en funcionamiento", "instalacao", "montagem"];
/** other work joined to a buying verb ("design, supply and build", "supply and maintenance of"): mixed as well */
const JOINED_WORK = ["design", "build", "building", "construction", "testing", "maintenance", "training", "repair", "implementation", "configuration", "integration",
  "conception", "formation", "entretien", "diseno", "construccion", "mantenimiento", "capacitacion", "implementacion", "construcao", "manutencao", "implementacao"];
/** joined to a buying verb without changing what is bought ("supply, transport and delivery of") */
const JOINED_NEUTRAL = ["transport", "transportation", "shipping", "unloading", "offloading", "distribution", "storage", "transporte", "descarga", "distribucion", "distribuicao"];

/** works that are always works, whatever follows */
const WORKS_STRONG = ["civil works", "road works", "roadworks", "earthworks", "building works", "construction works", "travaux", "obras?", "empreitada"];
/** works when used as the head of a phrase ("rehabilitation of", "school construction"), not as a describing word ("construction materials") */
const WORKS = ["works", "construction", "reconstruction", "rehabilitation", "renovation", "refurbishment", "repairs?", "repairing", "upgrading", "upgrade", "extension", "erection",
  "paving", "drilling", "dredging", "demolition", "excavation", "resurfacing", "landscaping", "remodelling", "remodeling", "retrofitting", "desilting",
  "refection", "amenagement", "forages?", "bitumage", "reparation",                                                         // French
  "construccion", "rehabilitacion", "mejoramiento", "ampliacion", "remodelacion", "reparacion", "pavimentacion", "reconstruccion", "adecuacion", "perforacion",   // Spanish
  "construcao", "reabilitacao", "reforma", "pavimentacao", "ampliacao", "requalificacao", "reparacao", "perfuracao"];        // Portuguese
/** buyer names that contain a works word: not a cue */
const WORKS_NOT = ["public works", "travaux publics", "obras publicas"];

/** services that are always services, whatever follows */
const SERVICE_STRONG = ["consultancy", "consultancies", "consulting", "consultants?", "advisory", "technical assistance", "capacity building", "software development",
  "insurance", "reinsurance", "labour", "labor", "manpower", "guards?", "guarding", "outsourcing",
  "development of (?:a |an |the )?(?:[a-z]+ ){0,2}(?:software|system|website|application|app|platform|database|portal|strategy|plan|policy|curriculum|manual|guidelines?)",
  "consultance", "assistance technique", "gardiennage", "assurances?", "main d'.uvre", "maitrise d'.uvre",                   // French
  "consultoria", "consultor(?:es|a|as)?", "asistencia tecnica", "interventoria", "seguros", "mano de obra", "asesoria",      // Spanish (consultoria is shared)
  "assistencia tecnica", "fiscalizacao", "mao de obra", "assessoria"];                                                      // Portuguese
/** the generic word: a service, but a buying verb after it wins ("servicio de suministro de combustible" buys fuel) */
const SERVICE_GENERIC = ["services", "service contract", "prestations? de services?", "prestations?", "services? de", "servicios?", "servicos?"];
/** services when used as the head of a phrase ("maintenance of", "feasibility study for"), not as a describing word ("cleaning materials") */
const SERVICE = ["feasibility", "stud(?:y|ies)", "surveys?", "surveying", "audit(?:s|ing)?", "supervision", "supervising", "training", "evaluation", "assessment",
  "monitoring", "maintenance", "servicing", "cleaning", "janitorial", "security", "hire", "hiring", "rental", "renting", "lease", "leasing", "catering",
  "transport", "transportation", "courier", "recruitment", "design", "internet", "connectivity", "bandwidth", "translation", "valuation", "mapping",
  "courses?", "workshops?", "seminars?",
  "land", "real estate", "office space", "premises", "terrains?", "terrenos?", "inmuebles?", "imovel", "imoveis",   // bought or rented, but nothing a supplier ships
  "etudes?", "formation", "entretien", "nettoyage", "location", "recrutement", "elaboration", "conception", "restauration",   // French
  "estudios?", "capacitacion", "mantenimiento", "limpieza", "vigilancia", "arrendamiento", "alquiler", "auditoria", "elaboracion", "diseno", "evaluacion", "transporte",   // Spanish
  "estudos?", "formacao", "capacitacao", "manutencao", "limpeza", "locacao", "aluguer", "aluguel", "elaboracao", "treinamento", "avaliacao"];   // Portuguese

/** a programme, project or policy title: money for development, not a purchase of goods (strong wording) */
const PROGRAMME_STRONG = ["(?:project|programme|program|projet|proyecto|projeto|programa)\\s*(?:phase\\s+\\w+\\s*)?$", "development (?:project|programme|program|policy|financing|operation)",
  "value chains?", "resilience", "governance", "reforms?", "strengthening", "institutional support", "additional financing", "budget support", "livelihoods?",
  "renforcement des capacites", "fortalecimiento", "fortalecimento", "desarrollo rural", "desenvolvimento rural", "developpement rural"];
/** weaker programme wording: decides only with low confidence */
const PROGRAMME_WEAK = ["projects?", "programmes?", "programs?", "projets?", "proyectos?", "projetos?", "programas?", "support (?:to|for)", "appui (?:a|au|aux)", "apoyo (?:a|al)", "apoio (?:a|ao)",
  "improving", "enhancing", "promoting", "initiative", "empowerment", "inclusion"];

/** bought as goods and services, or built and supplied by one contractor: mixed wherever it stands */
const MIXED_MARK = ["turnkey", "turn-key", "cles? en main", "llave en mano", "chave na mao", "epc", "design[- ]build", "design and build", "goods and (?:related |associated )?services",
  "works and supplies", "supply and fix", "and (?:related|associated|ancillary) services", "bienes y servicios", "biens et services", "bens e servicos"];
/** a framework or several lots: the labelling guide files these under mixed (low confidence: often plain goods) */
const FRAMEWORK = ["framework (?:agreement|contract|arrangement|purchase)s?", "framework", "accord[- ]cadre", "acuerdo marco", "convenio marco", "acordo[- ]quadro",
  "lots", "lotes", "multiple lots", "several lots"];

/** plain goods nouns: a goods verdict of low confidence when nothing else decides, and the proof a weak buying verb needs */
const GOODS_NOUN = ["equipment", "materials?", "supplies", "spare parts", "spares", "furniture", "vehicles?", "machinery", "machines", "reagents", "medicines", "drugs", "consumables",
  "tools", "kits", "goods", "stationery", "uniforms", "computers", "laptops", "generators", "fertilizers?", "fertilisers?", "vaccines", "fuel", "tyres", "tires",
  "equipements?", "materiels?", "materiaux", "mobilier", "vehicules?", "medicaments", "consommables", "pieces de rechange", "carburant", "engrais",   // French
  "equipos?", "materiales", "insumos", "mobiliario", "vehiculos?", "maquinaria", "medicamentos", "repuestos", "herramientas", "combustible", "bienes",   // Spanish
  "equipamentos?", "materiais", "material", "mobiliario", "veiculos?", "pecas", "ferramentas", "combustivel", "generos", "bens"];   // Portuguese

/** after a head word these show it is used as the thing done ("maintenance of", "study for", "training and"); a noun after it makes it a describing word */
const HEAD_FOLLOW = "(?:\\s*$|\\s*[,;:()\\-–/]|\\s+(?:of|for|on|in|at|to|and|or|de|d'|du|des|del|da|do|dos|das|pour|para|sur|sobre|en|em|et|y|e|a|au|aux|" +
  "services?|servicios?|servicos?|contracts?|projects?|programmes?|programs?|works|study|studies|firm|company|" +
  "preventive|corrective|routine|periodic|annual|general|preventiv[oa]s?|correctiv[oa]s?|corretiv[oa]s?|integral|predial|vial|rutinari[oa]|periodique|courant|tecnic[oa]s?)\\b)";
/** between two parts of a title: what comes after is added to what came before ("X and Y", "X including Y") */
const COORD = "(?:,|;|&|\\+|\\band\\b|\\bwith\\b|\\bincluding\\b|\\bplus\\b|\\bas well as\\b|\\bet\\b|\\bavec\\b|\\by compris\\b|\\bainsi que\\b|\\by\\b|\\be\\b|\\bcon\\b|\\bincluyendo\\b|\\bincluido\\b|\\bcom\\b|\\bincluindo\\b|\\bbem como\\b)";
/** where the thing bought ends and the purpose, place or buyer begins ("... for the district hospital", "... au profit de") */
const PURPOSE = "(?:\\s[-–]\\s|[:(\\[]|\\s(?:for|at|in|on|under|within|from|through|by|as per|according to|across|during|" +
  "pour|au profit|destinee?s?|dans|au|aux|aupres|para|en el|en la|en los|en las|con destino|destinad[oa]s?|em|no|na|nos|nas|junto)\\s|(?<!\\d)\\sto\\s(?!\\d))";
/** a part of a list that names a place or a buyer, not a product */
const PLACE = ["county", "district", "province", "region", "municipality", "city", "ministry", "hospital", "school", "university", "department", "office", "council", "state",
  "republic", "branch", "headquarters", "commune", "prefecture", "ministere", "hopital", "municipio", "provincia", "departamento", "alcaldia", "prefeitura", "secretaria", "ministerio"];
/** words dropped from the front of a product phrase */
const LEAD = ["the", "a", "an", "various", "assorted", "miscellaneous", "following", "new", "des", "de", "du", "la", "le", "les", "un", "une", "divers", "diverses",
  "los", "las", "el", "varios", "varias", "o", "os", "as", "um", "uma", "diversos", "diversas"];
/** a phrase made only of these says nothing about the product */
const EMPTY_PHRASE = ["goods", "items", "item", "products", "articles", "the following", "following", "bienes", "biens", "bens", "articulos", "artigos", "etc"];

// ---- helpers ----

/** lower case, accents removed, typographic apostrophes straightened; one character in, one character out */
export function fold(s: string): string {
  let out = "";
  for (const ch of s) {
    if (ch.length !== 1) { out += ch; continue; }
    if (ch === "’" || ch === "‘" || ch === "`" || ch === "´") { out += "'"; continue; }
    const b = ch.normalize("NFD")[0].toLowerCase();
    out += b.length === 1 ? b : ch;
  }
  return out;
}
const alt = (words: string[]) => `(?:${[...words].sort((a, b) => b.length - a.length).join("|")})`;
const word = (words: string[], flags = "g") => new RegExp(`(?<![a-z0-9])${alt(words)}(?![a-z0-9])`, flags);

const CHAIN_WORD = alt([...BUY, ...BUY_WEAK, ...INSTALL, ...JOINED_WORK, ...JOINED_NEUTRAL]);
// "supply of", "supply and delivery of", "supply, installation and commissioning of", "fourniture et pose de"
const CHAIN_RX = new RegExp(`(?<![a-z0-9])(?<!(?:water|power|electricity|energy|gas)\\s)${CHAIN_WORD}(?:\\s*(?:,\\s*(?:and\\s+|et\\s+|y\\s+|e\\s+)?|/|&|\\s(?:and|et|y|e|ou|or)\\s)\\s*${CHAIN_WORD})*` +
  `\\s+(?:of(?:\\s+the)?|del|de\\s+(?:la|las|los)(?![a-z])|de\\s+l'|de|des|du|dos|das|do|da|d')(?![a-z0-9])\\s*`, "g");
const BUY_RX = word(BUY, ""), WEAK_RX = word(BUY_WEAK, ""), INSTALL_RX = word(INSTALL, ""), JOINED_RX = word(JOINED_WORK, ""), NEUTRAL_RX = word(JOINED_NEUTRAL, "");
const GOODS_RX = word(GOODS_NOUN, ""), MIXED_RX = word(MIXED_MARK, ""), FRAMEWORK_RX = word(FRAMEWORK, "");
const PROG_STRONG_RX = word(PROGRAMME_STRONG, ""), PROG_WEAK_RX = word(PROGRAMME_WEAK, "");
const PURPOSE_RX = new RegExp(PURPOSE), COORD_RX = new RegExp(COORD), COORD_END_RX = new RegExp(`${COORD}\\s*(?:the\\s+|la\\s+|le\\s+|el\\s+|o\\s+|a\\s+)?$`);
const DE_BEFORE_RX = /(?:^|\s)(?:de|du|des|del|da|do|para|pour)\s+$|d'$/;
const SECTOR_NON_GOODS_RX = /works\b|construction|consult|services|repair|maintenance|engineering/i;

type Cls = "buy" | "weak" | "install" | "works" | "service" | "generic";
type Cue = { cls: Cls; at: number; end: number; text: string; mixed?: boolean };

/** every cue of a text, in order. Words inside a buying chain belong to the chain; describing words are left out. */
function cuesOf(f: string): Cue[] {
  const cues: Cue[] = [];
  for (const m of f.matchAll(CHAIN_RX)) {
    const t = m[0], buy = BUY_RX.test(t), weak = WEAK_RX.test(t), inst = INSTALL_RX.test(t), joined = JOINED_RX.test(t);
    if (buy || weak) cues.push({ cls: buy ? "buy" : "weak", at: m.index!, end: m.index! + t.length, text: t.trim(), mixed: inst || joined });
    else if (inst && !joined && !NEUTRAL_RX.test(t)) cues.push({ cls: "install", at: m.index!, end: m.index! + t.length, text: t.trim(), mixed: true });
  }
  const inChain = (i: number) => cues.some((c) => (c.cls === "buy" || c.cls === "weak" || c.cls === "install") && i >= c.at && i < c.end);
  const hidden = [...f.matchAll(word(WORKS_NOT))].map((m) => [m.index!, m.index! + m[0].length]);
  const add = (words: string[], cls: Cls, needsHead: boolean) => {
    for (const m of f.matchAll(word(words))) {
      const at = m.index!, end = at + m[0].length;
      if (inChain(at) || hidden.some(([a, b]) => at >= a && at < b) || cues.some((c) => at >= c.at && at < c.end)) continue;
      if (needsHead && !new RegExp("^" + HEAD_FOLLOW).test(f.slice(end))) continue;
      cues.push({ cls, at, end, text: m[0] });
    }
  };
  add(INSTALL, "install", true);        // "... including installation": named on its own, not in a buying chain
  add(SERVICE_STRONG, "service", false);
  add(SERVICE_GENERIC, "generic", false);
  add(WORKS_STRONG, "works", false);
  add(WORKS, "works", true);
  add(SERVICE, "service", true);
  return cues.sort((a, b) => a.at - b.at || b.end - a.end);
}

/** the reference numbers, lot numbers and dates of a notice, blanked out (same length is not needed here) */
function stripRefs(s: string): string {
  return s
    .replace(/[,;]?\s*[-–(]?\s*\b(?:lots?|lotes?)\s*(?:n[o°º.]*\s*)?(?:\d+[a-z]?|[ivx]+)\b(?:\s*(?:,|and|&|to|-|et|y|e|a)\s*(?:\d+|[ivx]+)\b)*\)?/gi, " ")
    .replace(/\b(?:in|into|en|em)\s+(?:\w+\s+)?\(?\d+\)?\s+(?:lots|lotes)\b/gi, " ")
    .replace(/\b(?:ref(?:erence)?|no|num|number|tender|rfq|itb|ifb|rfp|icb|ncb|contract)\.?\s*[:#]?\s*(?=[A-Z0-9\/\-_.]*\d)[A-Z0-9]+(?:[\/\-_.][A-Z0-9]+)+/gi, " ")
    .replace(/(?:n[°º]|#)\s*[A-Z0-9][A-Z0-9\/\-_.]*/gi, " ")
    .replace(/\b(?=[A-Z0-9\/_]*\d)(?=[A-Z0-9\/_]*[A-Z])[A-Z0-9]+(?:[\/_][A-Z0-9]+)+\b/g, " ")
    .replace(/\b(?=[A-Z0-9\-]*\d)[A-Z]{2,}[A-Z0-9]*(?:-[A-Z0-9]+){2,}\b/g, " ")
    .replace(/\b(?:FY\s?)?20[1-3]\d(?:\s*[\/–-]\s*(?:20)?\d{2})?(?=\s*(?:$|[,;:.)\]]))/g, " ")
    .replace(/\s+/g, " ").trim();
}

/** the thing bought, up to where the purpose, the place or the buyer begins */
function coreOf(object: string): string {
  const m = PURPOSE_RX.exec(fold(object));
  return (m ? object.slice(0, m.index) : object).trim();
}

/** one to three product phrases from the text that follows the buying cue */
function phrasesOf(object: string): string[] {
  const core = coreOf(stripRefs(object));
  const out: string[] = [];
  const parts = core.split(/\s*[,;]\s+|\s+(?:and|et|y|e|&)\s+|\s*\+\s*/i);
  parts.forEach((raw, i) => {
    let p = raw.replace(/["“”«»\[\]{}]/g, " ").replace(/\s+/g, " ").trim().replace(/^[\s.,;:\-–]+|[\s.,;:\-–]+$/g, "").replace(/\betc\.?$/i, "").trim();
    for (let again = true; again;) {
      again = false;
      const m = /^(\S+?)(?:\s+|')(.*)$/.exec(p);
      if (m && (LEAD.includes(fold(m[1])) || fold(m[1]) === "d" || fold(m[1]) === "l")) { p = m[2].trim(); again = true; }
    }
    const f = fold(p);
    if (p.length < 3 || !/[a-z]{3}/.test(f) || EMPTY_PHRASE.includes(f)) return;
    if (cuesOf(f).length || INSTALL_RX.test(f)) return;                 // the service or works part of a mixed title
    if (i > 0 && word(PLACE, "").test(f)) return;                       // ", Nairobi County"
    p = p.split(" ").slice(0, 8).join(" ");
    if (!out.some((x) => fold(x) === fold(p))) out.push(p);
  });
  return out.slice(0, 3);
}

type Verdict = Omit<TenderKind, "goods_phrases"> & { object?: string };

/** the wording of one text (a title or a description) */
function readWording(text: string): Verdict {
  const f = fold(text);
  const cues = cuesOf(f);
  const mixedMark = MIXED_RX.test(f), framework = FRAMEWORK_RX.test(f);
  const buys = cues.filter((c) => c.cls === "buy" || c.cls === "weak");
  // "servicio de suministro de combustible": the generic word before a buying verb does not decide
  const first = cues.find((c) => !(c.cls === "generic" && buys.some((b) => b.at > c.at)));
  if (!first) {
    if (mixedMark) return { kind: "mixed", confidence: "low", why: "wording for goods together with works or services (turnkey, design and build, goods and services)", object: text };
    if (PROG_STRONG_RX.test(f)) return { kind: "non_goods", confidence: "high", why: "a programme, project or policy title, with no buying wording" };
    if (GOODS_RX.test(f)) return { kind: "goods", confidence: "low", why: "names goods (equipment, materials, ...) but has no buying wording", object: text };
    if (PROG_WEAK_RX.test(f)) return { kind: "non_goods", confidence: "low", why: "reads like a programme or project title" };
    return { kind: "unknown", confidence: "low", why: "no buying, works or service wording found" };
  }

  if (first.cls === "install") return { kind: "mixed", confidence: "low", why: `installation named without a supply ("${first.text}"): the goods may be part of it`, object: text.slice(first.end) };

  if (first.cls === "works" || first.cls === "service" || first.cls === "generic") {
    const what = first.cls === "works" ? "works" : "a service";
    const later = cues.find((c) => (c.cls === "buy" || (c.cls === "weak" && c.mixed)) && c.at > first.at);
    // works: any supply named after them is part of the contract; a service: only a supply added with "and", "including", ...
    if (later && (first.cls === "works" || COORD_END_RX.test(f.slice(0, later.at))))
      return { kind: "mixed", confidence: "low", why: `${what} ("${first.text}") with a supply added ("${later.text}")`, object: text.slice(later.end) };
    if (first.cls === "works" && mixedMark) return { kind: "mixed", confidence: "low", why: `works ("${first.text}") under a turnkey or design-and-build contract`, object: "" };
    return { kind: "non_goods", confidence: "high", why: `the title is about ${what} ("${first.text}")${later ? ", the supply named later is its subject" : ""}` };
  }

  // a buying cue leads: what is bought?
  const object = text.slice(first.end), core = coreOf(object), fc = fold(core);
  const inner = cuesOf(fc).filter((c) => {
    if (c.cls === "buy" || c.cls === "weak") return false;
    // "matériaux de construction", "material de limpieza": the word after "de" describes the goods before it
    if (c.cls !== "generic" && c.at > 0 && DE_BEFORE_RX.test(fc.slice(0, c.at)) && /[a-z]{3}/.test(fc.slice(0, c.at).replace(DE_BEFORE_RX, ""))) return false;
    return true;
  });
  if (inner.length) {
    const c = inner[0], before = fc.slice(0, c.at);
    const goodsBefore = /[a-z]{3}/.test(before.replace(new RegExp(COORD, "g"), " ").replace(/\b(?:the|of|de|des|du|la|le|les|los|las|el)\b/g, " "));
    if (goodsBefore && COORD_RX.test(before))
      return { kind: "mixed", confidence: "high", why: `goods ("${first.text}") together with ${c.cls === "works" ? "works" : c.cls === "install" ? "installation" : "a service"} ("${c.text}")`, object };
    if (c.cls === "install") return { kind: "mixed", confidence: "low", why: `a supply with installation ("${c.text}")`, object: core.slice(c.end) };
    return { kind: "non_goods", confidence: "high", why: `what is bought is ${c.cls === "works" ? "works" : "a service"} ("${first.text} ${c.text}")` };
  }
  if (first.mixed) return { kind: "mixed", confidence: "high", why: `supply together with installation or other work ("${first.text}")`, object };
  if (mixedMark) return { kind: "mixed", confidence: "high", why: "supply under a turnkey, design-and-build or goods-and-services contract", object };
  if (first.cls === "weak" && !GOODS_RX.test(fc)) return { kind: "unknown", confidence: "low", why: `"${first.text}" is used for goods and for services alike, and the object names no known goods` };
  if (framework) return { kind: "mixed", confidence: "low", why: `supply ("${first.text}") under a framework or in several lots`, object };
  return { kind: "goods", confidence: "high", why: `buying wording ("${first.text}") with nothing but the goods after it`, object };
}

/** the procurement category of the notice (the tender column "nature"), in any of the four languages */
function readCategory(category: string): "goods" | "works" | "services" | "" {
  const c = fold(category);
  if (/consult|servic|prestation/.test(c)) return "services";
  if (/works|travaux|obras?|construction|empreitada/.test(c)) return "works";
  if (/goods|suppl|fournitures?|bienes|suministros?|bens|fornecimento|products/.test(c)) return "goods";
  return "";
}
/** CPV division (the first two digits): 45 is works; 50 to 98 are services; 03 to 44 and 48 (software packages) are
 *  goods. Division 51 (installation services) is a service that comes with a supply, so it does not decide alone. */
function readCpv(cpv: string): "goods" | "works" | "services" | "" {
  const m = /(?<!\d)(\d{2})(?:\d{6})?(?:-\d)?(?!\d)/.exec(cpv);
  if (!m) return "";
  const d = Number(m[1]);
  if (d === 45) return "works";
  if (d === 51) return "";
  if (d === 48 || (d >= 3 && d <= 44)) return "goods";
  if (d >= 50 && d <= 98) return "services";
  return "";
}

export function tenderKind(t: TenderKindInput): TenderKind {
  const title = String(t.title || "").normalize("NFC").replace(/\s+/g, " ").trim();
  const cat = readCategory(String(t.category || "")), cpv = readCpv(String(t.cpv || ""));
  const hint = cat || cpv, hintName = cat ? `procurement category "${String(t.category).trim().slice(0, 30)}"` : `CPV division ${/\d{2}/.exec(String(t.cpv || ""))?.[0] || ""}`;
  let v: Verdict = title ? readWording(title) : { kind: "unknown", confidence: "low", why: "no title" };

  if (hint) {
    const w = v;
    if (hint === "goods") {
      if (w.kind === "non_goods" && w.confidence === "high") v = { kind: "mixed", confidence: "low", why: `${hintName} says goods, but ${w.why}`, object: "" };
      else if (w.kind === "mixed") v = { ...w, confidence: "high", why: `${hintName}; ${w.why}` };
      else v = { kind: "goods", confidence: "high", why: `${hintName}${w.kind === "goods" ? "; " + w.why : ""}`, object: w.object ?? title };
    } else {
      if (w.kind === "goods" && w.confidence === "high" || w.kind === "mixed") v = { kind: "mixed", confidence: "low", why: `${hintName} says ${hint}, but ${w.why}`, object: w.object };
      else v = { kind: "non_goods", confidence: "high", why: `${hintName}${w.kind === "non_goods" ? "; " + w.why : ""}` };
    }
  } else if (v.kind === "unknown") {
    // the title says nothing: the description may, and after it the sector; neither is trusted as much as a title
    const d = String(t.description || "").replace(/\s+/g, " ").trim().slice(0, 300);
    const dv = d ? readWording(d) : null;
    if (dv && dv.kind !== "unknown") v = { ...dv, confidence: "low", why: `from the description: ${dv.why}` };
    else if (SECTOR_NON_GOODS_RX.test(String(t.sector || ""))) v = { kind: "non_goods", confidence: "low", why: `nothing in the title decides; the sector is a works or services sector` };
  }

  const phrases = (v.kind === "goods" || v.kind === "mixed") && v.object ? phrasesOf(v.object) : [];
  return { kind: v.kind, confidence: v.confidence, why: v.why, goods_phrases: phrases };
}
