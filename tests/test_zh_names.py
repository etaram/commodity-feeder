"""Pure checks for leads/zh_names.py and its use in the website checks."""
from leads.company_check import name_match
from leads.refine import name_in_domain
from leads.zh_names import cores, domain_candidates, page_names


def test_cores_and_domains():
    assert cores("湖南华菱钢铁集团有限责任公司") == ["华菱钢铁", "华菱"]
    assert cores("宁德时代新能源科技股份有限公司")[-1] == "宁德时代"
    assert "hualing.com" in domain_candidates("湖南华菱钢铁集团有限责任公司")
    assert "huawei.com" in domain_candidates("华为技术有限公司")


def test_page_and_domain_checks():
    assert page_names("华为技术有限公司", "华为技术有限公司 - 官网", "")[0] == "high"
    assert page_names("华为技术有限公司", "Huawei", "欢迎来到华为，华为是...")[0] in ("high", "partial")
    assert page_names("华为技术有限公司", "Example", "nothing here")[0] == "none"
    assert name_match("湖南华菱钢铁集团有限责任公司", "华菱钢铁集团", "")[0] == "high"
    assert name_in_domain("湖南华菱钢铁集团有限责任公司", "hualing.com") and not name_in_domain("湖南华菱钢铁集团有限责任公司", "baosteel.com")
    assert name_in_domain("Acme Valves Ltd", "acmevalves.com")  # Latin names unchanged


if __name__ == "__main__":
    test_cores_and_domains(); test_page_and_domain_checks()
    print("zh names: all checks passed")
