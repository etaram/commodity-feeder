"""leads/gleif_bulk.py: name normalisation, Level 1 + Level 2 match on saved Golden Copy rows (column layout of the
2026-11-12 LEI-CDF 3.1 CSV and RR-CDF CSV), ambiguity rule, zip streaming. No network."""
import csv
import io
import zipfile

from leads import gleif_bulk as G

L1_HEADER = ["LEI", "Entity.LegalName", "Entity.LegalName.xmllang", "Entity.OtherEntityNames.OtherEntityName.1",
             "Entity.LegalAddress.City", "Entity.LegalAddress.Country", "Entity.HeadquartersAddress.Country",
             "Entity.RegistrationAuthority.RegistrationAuthorityID", "Entity.RegistrationAuthority.RegistrationAuthorityEntityID",
             "Entity.EntityStatus", "Registration.RegistrationStatus"]
L1 = [
    ["5299000J2N45DDNE4Y28", "Siemens Energy Global GmbH & Co. KG", "de", "", "Munich", "DE", "DE", "RA000304", "HRA 115419", "ACTIVE", "ISSUED"],
    ["W38RGI023J3WT1HWRP32", "Siemens Energy AG", "de", "", "Munich", "DE", "DE", "RA000304", "HRB 252581", "ACTIVE", "ISSUED"],
    ["549300ABCDEF00000001", "Acme Trading Co., Ltd.", "en", "", "Nairobi", "KE", "KE", "RA000418", "PVT-123", "ACTIVE", "ISSUED"],
    ["549300ABCDEF00000002", "ACME TRADING LIMITED", "en", "", "Mombasa", "KE", "KE", "RA000418", "PVT-999", "ACTIVE", "ISSUED"],
    ["549300ABCDEF00000003", "PT Wijaya Karya (Persero) Tbk", "id", "Wijaya Karya", "Jakarta", "ID", "ID", "RA000394", "AHU-1", "ACTIVE", "ISSUED"],
    ["549300ABCDEF00000004", "Old Closed Ltd", "en", "", "Accra", "GH", "GH", "", "", "INACTIVE", "RETIRED"],
]
RR_HEADER = ["Relationship.StartNode.NodeID", "Relationship.StartNode.NodeIDType", "Relationship.EndNode.NodeID",
             "Relationship.EndNode.NodeIDType", "Relationship.RelationshipType", "Relationship.RelationshipStatus"]
RR = [["5299000J2N45DDNE4Y28", "LEI", "W38RGI023J3WT1HWRP32", "LEI", "IS_DIRECTLY_CONSOLIDATED_BY", "ACTIVE"],
      ["5299000J2N45DDNE4Y28", "LEI", "W38RGI023J3WT1HWRP32", "LEI", "IS_ULTIMATELY_CONSOLIDATED_BY", "ACTIVE"]]


def _zip(tmp_path, name, header, rows):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(header); w.writerows(rows)
    p = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(f"{name}.csv", buf.getvalue())
    return p


def test_norm_name():
    assert G.norm_name("Acme Trading Co., Ltd.") == "acme trading"
    assert G.norm_name("ACME TRADING LIMITED") == "acme trading"
    assert G.norm_name("PT Wijaya Karya (Persero) Tbk") == "wijaya karya persero"
    assert G.norm_name("Siemens Energy Global GmbH & Co. KG") == "siemens energy global"
    assert G.norm_name("Société Générale S.A.") == "societe generale"


def test_match_with_parent_and_ambiguity(tmp_path):
    uni = tmp_path / "u.csv"
    uni.write_text("supplier,country,website,address,region\n"
                   "SIEMENS ENERGY GLOBAL GMBH & CO KG,DEU,https://siemens-energy.com,Munich,Europe\n"
                   "Acme Trading Ltd,KEN,,Nairobi,Sub-Saharan Africa\n"
                   "Wijaya Karya,IDN,https://wika.co.id,Jakarta,Southeast Asia\n"
                   "Old Closed Limited,GHA,,,Sub-Saharan Africa\n", encoding="utf-8")
    idx, meta = G.universe_keys(uni)
    rr = G.read_rr(_zip(tmp_path, "rr", RR_HEADER, RR))
    matches, stats = G.match_lei2(G._lei2_rows(_zip(tmp_path, "lei2", L1_HEADER, L1)), idx, rr)
    s = matches["SIEMENS ENERGY GLOBAL GMBH & CO KG|DEU"]
    assert s["lei"] == "5299000J2N45DDNE4Y28" and s["ra"] == "RA000304" and s["city"] == "Munich"
    assert s["ultimate_parent_lei"] == "W38RGI023J3WT1HWRP32" and s["ultimate_parent_name"] == "Siemens Energy AG"
    assert "Acme Trading Ltd|KEN" not in matches and stats["ambiguous"] == 1      # two active LEIs, same name and country
    assert matches["Wijaya Karya|IDN"]["matched_on"] == "other name"
    assert "Old Closed Limited|GHA" not in matches                                # inactive entity
    sample = G.precision_sample(matches, meta, n=50)
    assert len(sample) == 2 and all(x["city_in_address"] for x in sample)
