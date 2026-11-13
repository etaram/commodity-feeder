"""Transnet and Bonfire collectors parse the JSON shape seen from the server on 13 Nov 2026. No network."""


def test_transnet_open_only_and_fields():
    from leads import transnet
    js = {"success": True, "result": [
        {"nameOfTender": "NGQURA MANGANESE EXPORT CORRIDOR PSP", "descriptionOfTender": "private sector partner", "tenderNumber": "TCC/2026/08/0001/114626/RFQ",
         "institution": "TCC", "closingDate": "02/26/2027 4:00:00 PM", "publishedDate": "09/23/2026 10:00:00 AM", "tenderStatus": "Advertised"},
        {"nameOfTender": "OLD", "tenderNumber": "TFR/1", "closingDate": "01/05/2026 10:00:00 AM", "tenderStatus": "Advertised"},
        {"nameOfTender": "CANCELLED ONE", "tenderNumber": "TFR/2", "closingDate": "01/05/2027 10:00:00 AM", "tenderStatus": "Cancelled"},
        {"nameOfTender": "", "tenderNumber": "TFR/3"}]}
    rows = transnet.parse(js, "2026-11-13")
    assert [r["id"] for r in rows] == ["TRANSNET-TCC-2026-08-0001-114626-RFQ", "TRANSNET-TFR-1"]
    r = rows[0]
    assert r["country"] == "ZAF" and r["buyer"] == "Transnet Corporate Centre"
    assert r["deadline"] == "2027-02-26" and r["published"] == "2026-09-23"
    # fetch() keeps only a future deadline; the old row is dropped there
    assert [x for x in rows if x["deadline"] >= "2026-11-13"][0] is r


def test_bonfire_parse():
    from leads import bonfire
    js = {"success": 1, "payload": {"projects": {
        "255839": {"ProjectID": "255839", "ReferenceID": "Bid # 6000003483", "ProjectVisibilityID": "1",
                   "ProjectName": "Bid # 6000003483 -Electrical Equipment Inspecting and Testing", "DateClose": "2026-11-16 16:00:00"},
        "1": {"ProjectID": "1", "ReferenceID": "X", "ProjectVisibilityID": "2", "ProjectName": "private one", "DateClose": "2026-12-01 10:00:00"}}}}
    rows = bonfire.parse(js, "panynj", "Port Authority of New York and New Jersey", "USA", "2026-11-13")
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "BONFIRE-panynj-255839" and r["deadline"] == "2026-11-16" and r["country"] == "USA"
    assert r["title"].startswith("Bid # 6000003483") and r["link"] == "https://panynj.bonfirehub.com/opportunities/255839"


def test_eskom_rules():
    from leads import eskom
    js = [{"TENDER_ID": 96416, "REFERENCE": "E3621DXKZNOU", "HEADER_DESC": "RFI to design, manufacture and install 88kV-132kV GIS switchgear",
           "DESCRIPTION": "DISTRIBUTION", "CLOSING_DATE": "2026-11-30T10:00:00", "PUBLISHEDDATE": "2026-09-30T09:00:00", "PUBLISH": "Y",
           "Audience": "All Suppliers", "EMAIL": "someone@eskom.co.za", "E_TENDERING": True},
          {"TENDER_ID": 2, "REFERENCE": "MWP2457DXCancellatio", "HEADER_DESC": "Supply of gases. Cancellation", "CLOSING_DATE": "2027-05-28T10:00:00",
           "PUBLISHEDDATE": "2026-10-28T09:37:08", "PUBLISH": "Y"},
          {"TENDER_ID": 3, "REFERENCE": "OLD", "HEADER_DESC": "Cleaning services 48 months", "CLOSING_DATE": "2027-02-22T13:33:00",
           "PUBLISHEDDATE": "2023-05-22T13:35:12", "PUBLISH": "Y"},
          {"TENDER_ID": 4, "REFERENCE": "R", "HEADER_DESC": "Regret letter smart meters", "CLOSING_DATE": "2027-10-22T10:00:00",
           "PUBLISHEDDATE": "2026-10-22T10:00:00", "PUBLISH": "Y"}]
    rows = eskom.parse(js, "2026-11-13")
    assert [r["id"] for r in rows] == ["ESKOM-96416"]
    r = rows[0]
    assert r["deadline"] == "2026-11-30" and r["country"] == "ZAF" and r["buyer"] == "Eskom Holdings SOC Ltd - Distribution"
    assert "eskom.co.za" not in r["contact"] and "e-tendering" in r["notice_type"]


KKJ_XML = """<?xml version="1.0" encoding="utf-8" ?><Results><Version>1.0</Version><SearchResults><SearchHits>2</SearchHits>
<SearchResult><ResultId>1</ResultId><Key><![CDATA[eWFtYW5hc2hpL3lhbWFuYXNoaV9wcmVmLzIwMjYK]]></Key>
<ExternalDocumentURI><![CDATA[https://www.pref.yamanashi.jp/documents/128542/koukoku.pdf]]></ExternalDocumentURI>
<ProjectName>ＥＷＳ実習装置に係る一般競争入札の公告</ProjectName><LgCode>19</LgCode><PrefectureName>山梨県</PrefectureName>
<OrganizationName>山梨県</OrganizationName><CftIssueDate>2026-11-12T00:00:00+09:00</CftIssueDate><Category>物品</Category>
<ProcedureType>一般競争入札</ProcedureType><OpeningTendersEvent>2026-12-23T11:30:00+09:00</OpeningTendersEvent></SearchResult>
<SearchResult><ResultId>2</ResultId><Key>abc</Key><ProjectName>期限なし</ProjectName><OrganizationName>X市</OrganizationName></SearchResult>
</SearchResults></Results>"""


def test_kkj_parse():
    from leads import kkj
    rows, hits = kkj.parse(KKJ_XML, "2026-11-13")
    assert hits == 2 and len(rows) == 2
    r = rows[0]
    # only an opening date in the data: closing unknown, opening kept separately, not admitted as OPEN
    assert r["country"] == "JPN" and r["deadline"] == "" and r["opening"] == "2026-12-23" and r["published"] == "2026-11-12"
    assert r["deadline_basis"] == "unknown"
    assert r["nature"] == "supplies" and r["lang"] == "ja" and r["link"].endswith("koukoku.pdf")
    assert rows[1]["deadline"] == ""          # no date: fetch() does not count it as open


def test_kkj_text_deadline():
    import datetime as dt
    from leads import kkj
    desc = "２ 入札参加資格の確認申請期間 公告の日～令和８年１２月７日(月) ３ 入札日時 令和８年１２月２３日(水) 午前１１時３０分"
    assert kkj.text_deadline(desc, dt.date(2026, 11, 13)) == "2026-12-23"
    assert kkj.text_deadline("入札日時 令和８年１０月１日", dt.date(2026, 11, 13)) == ""
    assert kkj.text_deadline("令和８年１２月２３日 only a date, no deadline word", dt.date(2026, 11, 13)) == ""


def test_bidnet_parse():
    from pathlib import Path
    from leads import bidnet
    page = (Path(__file__).parent / "samples" / "bidnet_open_p2.html").read_text(encoding="utf-8")
    rows = bidnet.parse(page, "2026-11-13")
    assert len(rows) == 4
    r = rows[0]
    assert r["title"] == "Concrete Raising" and r["deadline"] == "2026-12-01" and r["published"] == "2026-11-12"
    assert r["country"] == "USA" and "Texas" in r["buyer"] and r["id"] == "BIDNET-444233674884"
    assert r["link"].startswith("https://www.bidnetdirect.com/texas/solicitations/open-bids/")


def test_snapshot_drops_removed_and_dates_are_real(tmp_path, monkeypatch):
    from leads import common
    monkeypatch.setattr(common, "CACHE", tmp_path)
    a = {"id": "T-1", "deadline": "2026-12-01"}; b = {"id": "T-2", "deadline": "2026-12-02"}
    common.snapshot("transnet", [a, b])
    keep, _ = common.snapshot("transnet", [a])               # T-2 cancelled or removed upstream
    assert [r["id"] for r in keep] == ["T-1"]
    assert common.valid_date("2026-99-99") == "" and common.valid_date("2026-12-01T10:00") == "2026-12-01"


def test_transnet_schema_change_raises():
    import pytest
    from leads import transnet
    with pytest.raises(ValueError):
        transnet.parse({"success": False, "message": "error"}, "2026-11-13")


def test_bonfire_all_hubs_fail_raises(monkeypatch):
    import pytest
    from leads import bonfire

    class S:
        def get(self, *a, **k):
            raise ConnectionError("down")
    monkeypatch.setattr(bonfire, "session", lambda: S())
    monkeypatch.setattr(bonfire, "HUBS", [("x1", "X", "USA"), ("x2", "Y", "USA")])
    with pytest.raises(RuntimeError):
        bonfire.fetch()


def test_bonfire_rejects_impossible_date():
    from leads import bonfire
    js = {"success": 1, "payload": {"projects": {"1": {"ProjectID": "1", "ReferenceID": "R", "ProjectVisibilityID": "1",
                                                       "ProjectName": "Road salt supply", "DateClose": "2026-99-99 10:00:00"}}}}
    assert bonfire.parse(js, "h", "B", "USA", "2026-11-13")[0]["deadline"] == ""


def test_kkj_closing_needs_stated_evidence():
    import datetime as dt
    from leads import kkj
    t = dt.date(2026, 11, 13)
    # closing stated 12 Nov, opening 1 Dec: closed, not admitted
    c = kkj.text_closing("入札書の提出期限 令和８年１１月１２日 開札日時 令和８年１２月１日")
    assert c == "2026-11-12"
    assert not kkj.admitted({"deadline": c, "deadline_basis": "text_closing"}, t)
    # start-only or opening-only: unknown closing, never admitted
    assert not kkj.admitted({"deadline": "", "deadline_basis": "unknown", "opening": "2026-12-20"}, t)
    # conflicting closing dates: the earliest wins
    assert kkj.text_closing("提出期限 2026年11月20日 ... 受領期限 2026年11月18日") == "2026-11-18"
    # same-day closing still open on that date
    assert kkj.admitted({"deadline": "2026-11-13", "deadline_basis": "text_closing"}, t)
    assert kkj.text_closing("開札日時 令和８年１２月１日") == ""


def test_ccgp_detail():
    from leads import ccgp
    page = "<p>并于2026年12月08日09点00分（北京时间）前递交投标文件。</p><p>预算金额：125(万元)</p><p>10、是否可采购进口产品：否</p><td>开标时间</td><td>2026年11月16日 00:00</td>"
    assert ccgp.detail(page) == ("2026-12-08", 1250000, "no")
    assert ccgp.detail("截止时间：2026年12月08日09点00分 预算金额：￥980,000.00元")[:2] == ("2026-12-08", 980000)
    assert ccgp.detail("no dates here") == ("", "", "")


def test_buyspeed_parse():
    from leads import buyspeed
    real = ('<thead><tr><th id="a" class="ui-state-default" aria-label="Bid Solicitation #" scope="col">Bid Solicitation #</th>'
            '<th id="b" aria-label="Organization Name" scope="col">Organization Name</th><th aria-label="Description" scope="col">Description</th>'
            '<th aria-label="Bid Opening Date" scope="col">Bid Opening Date</th><th aria-label="Status" scope="col">Status</th></tr></thead>'
            '<tr data-ri="0" class="ui-widget-content"><td role="gridcell"><a href="/bso/external/bidDetail.sda?docId=BD-9">BD-9</a></td>'
            '<td role="gridcell">MassDOT</td><td role="gridcell">Guardrail supply</td><td role="gridcell">12/15/2026 02:00:00 PM</td><td role="gridcell">Sent</td></tr>')
    assert buyspeed.parse(real, "https://www.commbuys.com", "US-MA", "Commonwealth of Massachusetts", "2026-11-13")[0]["deadline"] == "2026-12-15"
    page = ('<th role="columnheader"><span>Bid Solicitation #</span></th><th role="columnheader">Organization Name</th>'
            '<th role="columnheader">Description</th><th role="columnheader">Bid Opening Date</th><th role="columnheader">Status</th>'
            '<tr data-ri="0" class="ui-widget-content"><td role="gridcell"><a href="/bso/external/bidDetail.sda?docId=BD-27-1&amp;external=true">BD-27-1</a></td>'
            '<td role="gridcell">Department of Transportation</td><td role="gridcell">Road salt supply</td><td role="gridcell">12/01/2026 02:00:00 PM</td><td role="gridcell">Sent</td></tr>'
            '<tr data-ri="1"><td>BD-27-2</td><td>X</td><td>Old bid</td><td>11/01/2026</td><td>Cancelled</td></tr>')
    rows = buyspeed.parse(page, "https://www.commbuys.com", "US-MA", "Commonwealth of Massachusetts", "2026-11-13")
    assert len(rows) == 1
    r = rows[0]
    assert r["deadline"] == "2026-12-01" and r["title"] == "Road salt supply" and r["country"] == "USA"
    assert r["link"].startswith("https://www.commbuys.com/bso/external/bidDetail.sda?docId=BD-27-1") and r["id"] == "BSO-MA-BD-27-1"


def test_taiwan_parse():
    from leads import taiwan
    page = ('<table><tbody><tr><td>search form</td></tr></tbody></table><table><tbody> <tr class="tb_b2"> <td class="no_blank"> 1 </td> <td> 新北市三重區碧華國民小學 </td> '
            '<td> BHES1150903<span style="color:red"> (更正公告)</span> <br> <a href="/prkms/urlSelector/common/tpam?pk=NzEzODUxMjM="> <u> '
            '<span id="1"><script>var hw = Geps3.CNS.pageCode2Img("115學年度上學期午餐食材採購");</script></span></u></a> </td>'
            '<td> 01 </td><td> 公開招標 </td><td> 財物類 </td><td> 115/11/12 </td><td> 115/11/24 </td><td> 1,250,000 </td><td></td></tr></tbody></table>')
    rows = taiwan.parse(page, "2026-11-13")
    assert len(rows) == 1
    r = rows[0]
    assert r["buyer"] == "新北市三重區碧華國民小學" and r["title"] == "115學年度上學期午餐食材採購"
    assert r["deadline"] == "2026-11-24" and r["published"] == "2026-11-12" and r["nature"] == "goods"
    assert r["value"] == 1250000 and r["currency"] == "TWD" and r["link"].endswith("tpam?pk=NzEzODUxMjM=")
    assert "corrected" in r["notice_type"]


def test_hk_gld_parse():
    from leads import hk_gld
    x = ('<TenderNotice><DepartmentEnglish>Government Logistics Department</DepartmentEnglish>'
         '<TenderNoticeRecord><TenderNo>AD200712025</TenderNo><IssueDateTime>2026-10-02 00:00:00</IssueDateTime>'
         '<ClosingDateTime>2026-11-17 12:00:00</ClosingDateTime><SubjectEnglish>Supply of mobile libraries</SubjectEnglish>'
         '<DepartmentEnglish>Electrical and Mechanical Services Department</DepartmentEnglish><Status>I</Status>'
         '<Link>https://pcms2.gld.gov.hk/iprod/#/STA00303?tenderReferenceNumber=AD200712025</Link></TenderNoticeRecord>'
         '<TenderNoticeRecord><TenderNo>LC/1</TenderNo><ClosingDateTime>2026-11-17 12:00:00</ClosingDateTime>'
         '<SubjectEnglish>Tender for the Grant of a Permit to Conduct the Restaurant Business</SubjectEnglish><Status>I</Status></TenderNoticeRecord></TenderNotice>')
    rows = hk_gld.parse(x, "2026-11-13")
    assert rows[0]["deadline"] == "2026-11-17" and rows[0]["country"] == "HKG" and rows[0]["stage"] == "tender"
    assert rows[0]["buyer"].startswith("Electrical") and rows[1]["stage"] == "concession"
