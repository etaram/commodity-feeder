export async function supplierSearch() { return { total: 2, origins: [], query: "", values: [["supplier", "country", "type", "match", "match_why"], ["Grain SA", "ZAF", "goods supplier", "supported", "own description"], ["Filtro", "TUR", "goods supplier", "incompatible", "x"]] }; }
export async function searchTenders() { return [["id", "title", "country"], ["T1", "Supply of white maize", "KEN"]]; }
export async function searchTendersSmart() { return { values: await searchTenders(), total: 1 }; }
export async function getRange(_name: string) { return [["currency", "usd_per_unit"], ["EUR", "1.1"]]; }
