from leads import local_works


def test_labels_local_works_not_supply():
    r = {"country": "IND", "title": "CC Road And Nali Nirman Work", "notice_type": "Open Tender"}
    assert local_works.label(r) and r["notice_type"] == "Open Tender | local civil works" and r["nature"] == "works"
    assert not local_works.label({"country": "IND", "title": "SUPPLY OF SCIENCE MATERIAL TO THE GOVERNMENT ASHRAM SCHOOLS"})
    assert not local_works.label({"country": "USA", "title": "Repair of roof"})
    r = {"country": "IND", "title": "Restoration of BT Road at Ward no 3"}
    local_works.label(r); local_works.label(r)
    assert r["notice_type"] == "local civil works"
