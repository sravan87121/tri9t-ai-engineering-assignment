from app.parser import parse_pdf, parent_number

def test_skipped_parent():
    assert parent_number('2.1.1.1', {'2','2.1'}) == '2.1'

def test_duplicate_titles_remain_distinct():
    nodes, _ = parse_pdf('data/ct200_manual.pdf')
    assert [n['key'] for n in nodes if n['title']=='Error Codes'] == ['4.2','7.1']

def test_out_of_order_and_lists():
    nodes, _ = parse_pdf('data/ct200_manual.pdf')
    keys = [n['key'] for n in nodes]
    assert keys.index('3.4') < keys.index('3.3')
    assert len([n for n in nodes if n['parent']=='root']) == 8
    assert 'Hypertensive Crisis' in next(n['text'] for n in nodes if n['key']=='3.3')

def test_cross_page_and_tables():
    nodes, _ = parse_pdf('data/ct200_manual_v2.pdf')
    by = {n['key']:n for n in nodes}
    assert 'cannot be silenced' in by['4.3']['text']
    assert '1.5 seconds' in by['4.2']['text']
    assert 'E6' in by['4.2']['text']
    assert any(b['kind']=='table_row' for b in by['4.2']['blocks'])
