from app.parser.address_parser import parse_address


def test_parse_basic():
    raw = "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 张三 15900001234 310052"
    result = parse_address(raw).model_dump()

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
    raw = "北京市朝阳区建国路88号"
    result = parse_address(raw).model_dump()

    assert result["province"] == "北京市"
    assert result["city"] == "北京市"
    assert result["district"] == "朝阳区"

    # ensure street content preserved when no explicit recipient is present
    assert result["street"] == "建国路88号"
    assert result["recipient"] is None


def test_parse_beijing_shahe_priority():
    raw = "北京沙河白各庄新村东区5号楼5单元803 张三 1590000124 102206"
    result = parse_address(raw).model_dump()

    assert result["province"] == "北京市"
    assert result["city"] == "北京市"
    assert result["district"] == "昌平区"

    # postal code should trust the user input once area matches
    assert result["postal_code"] == "102206"
    assert result["postal_mismatch"] is False


def test_parse_wrong_postal_flags_mismatch():
    raw = "河南郑州二七区庆丰街1号 410000"
    result = parse_address(raw).model_dump()

    assert result["province"] == "河南省"
    assert result["city"] == "郑州市"
    assert result["district"] == "二七区"
    assert result["postal_code"] == "450000"
    assert result["postal_mismatch"] is True


def test_parse_generic_district_prefers_context():
    raw = "安徽合肥白各庄新村东区5号楼5单元803 张三 1590000124 102206"
    result = parse_address(raw).model_dump()

    assert result["province"] == "安徽省"
    assert result["city"] == "合肥市"
    assert result["postal_mismatch"] is True
    assert result["postal_code"] == "102206"
