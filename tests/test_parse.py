from app.parser.address_parser import parse_address


def test_parse_basic():
    raw = "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 张三 15900001234 310052"
    result = parse_address(raw)

    assert result["province"] == "浙江省"
    assert result["city"] == "杭州市"
    assert result["district"] == "滨江区"

    # street should still contain 长河街道 / 江南大道 etc.
    assert "江南大道" in (result["street"] or "")

    # phone extracted
    assert result["phone"] == "15900001234"

    # recipient extracted
    assert result["recipient"] == "张三"

    # has postal code (either from text or metadata)
    assert result["postal_code"] == "310052"

    # deliverable heuristic should be True
    assert result["deliverable"] is True

    assert 0.5 <= result["confidence"] <= 1.0


def test_parse_without_recipient():
    raw = "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 15900001234 310052"
    result = parse_address(raw)

    assert result["recipient"] is None
    assert result["phone"] == "15900001234"
    assert "江南大道" in (result["street"] or "")


def test_parse_trailing_name_with_marker():
    raw = "北京市昌平区沙河镇白各庄102号张三收 13800001234 102206"
    result = parse_address(raw)

    assert result["province"] == "北京市"
    assert result["city"] == "北京市"
    assert result["district"] == "昌平区"
    assert result["recipient"] == "张三"
    assert "沙河镇" in (result["street"] or "")
    assert result["phone"] == "13800001234"
    assert result["postal_code"] == "102206"


def test_parse_prefers_explicit_tokens_over_conflicting_postal():
    raw = "辽宁大连白各庄新村东区5号楼5单元803 张三 1590000124 102206"
    result = parse_address(raw)

    assert result["province"] == "辽宁省"
    assert result["city"] == "大连市"
    assert result["district"] is None
    assert result["recipient"] == "张三"
    assert result["phone"] is None
    assert result["postal_code"] == "110000"
    assert result["postal_mismatch"] is True
    assert "白各庄新村东区" in (result["street"] or "")


def test_parse_prefers_mainland_district_over_non_mainland_city():
    raw = "内蒙卓资白各庄新村东区5号楼5单元803 张三 1590000124 102206"
    result = parse_address(raw)

    assert result["province"] == "内蒙古自治区"
    assert result["city"] == "乌兰察布市"
    assert result["district"] == "卓资县"
    assert result["recipient"] == "张三"
    assert result["postal_code"] == "012300"


def test_parse_taiwan_with_mainland_postal_flags_mismatch():
    raw = "台湾台南白各庄新村东区5号楼5单元803 张三 1590000124 102206"
    result = parse_address(raw)

    assert result["province"] == "台南市"
    assert result["postal_code"] == "722001"
    assert result["postal_mismatch"] is True


def test_parse_postal_adjacent_to_chinese_characters():
    raw = "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 张三 15900001234 邮编310052号"
    result = parse_address(raw)

    assert result["postal_code"] == "310052"
    assert result["postal_mismatch"] is False
