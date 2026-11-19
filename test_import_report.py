from pathlib import Path

from import_report import Columns, generate, read_import, validate_import, write_retry_csv


HERE = Path(__file__).parent


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        return read_import(source)


def test_report_contains_four_sections_and_exposes_only_expected_matches(tmp_path):
    report = generate(HERE / 'example-import.csv', HERE / 'example-snapshot.csv', tmp_path)
    assert report.total == 8
    assert report.counts == {'新增': 4, '更新': 1, '冲突': 2, '错误': 1}
    assert report.errors == [(7, 'name', '必填字段为空')]
    assert {row[:2] for row in report.duplicates} == {
        ('TAG-NEW-A1', 'TAG-OLD-A1'), ('TAG-NEW-B1', 'TAG-OLD-B1'), ('TAG-NEW-C1', 'TAG-OLD-C1'),
    }
    assert all(float(row[2]) > 0.85 for row in report.duplicates)
    content = (tmp_path / 'import-report.html').read_text(encoding='utf-8')
    assert all(f'<h2>{name}</h2>' in content for name in ('汇总', '错误', '冲突', '疑似重复'))
    assert '现有地址' in content
    assert '导入地址 &lt;script&gt;' in content
    assert '<script>' not in content


def test_edit_and_reimport_keeps_headers_quoted_fields_and_the_fix(tmp_path):
    generate(HERE / 'example-import.csv', HERE / 'example-snapshot.csv', tmp_path)
    path = tmp_path / 'retry-import.csv'
    fields, rows = read(path)
    assert (fields, rows) == read(HERE / 'example-import.csv')
    assert rows[4]['notes'] == '主营产品有中文, 还包含 "引号"'
    rows[5]['name'] = '间歇校准'
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        write_retry_csv(output, fields, rows)
    retry_fields, retry_rows = read(path)
    assert retry_fields == fields
    assert retry_rows[5]['name'] == '间歇校准'
    retry_report = validate_import(retry_rows, read(HERE / 'example-snapshot.csv')[1])
    assert not retry_report.errors
    assert retry_report.counts['新增'] == 5


def test_exact_similarity_boundary_is_excluded_unless_aliases_match():
    incoming = [{'code': 'A', 'name': 'abcdefghijklmnopqRST', 'aliases': ''}]
    baseline = [{'code': 'B', 'name': 'abcdefghijklmnopqXYZ', 'aliases': ''}]
    assert validate_import(incoming, baseline).duplicates == []
    incoming[0]['aliases'] = ' 门店运营 '
    baseline[0]['aliases'] = '门店运营'
    assert validate_import(incoming, baseline).duplicates == [('A', 'B', '0.850', '门店运营')]


def test_duplicate_check_compares_new_and_updated_values_in_either_input_order():
    snapshot = [{'code': 'A', 'name': 'Unrelated legacy title', 'aliases': ''}]
    updated = {'code': 'A', 'name': 'Customer Support Desk A', 'aliases': ''}
    added = {'code': 'B', 'name': 'Customer Support Desk B', 'aliases': ''}
    for rows in ([added, updated], [updated, added]):
        report = validate_import(rows, snapshot)
        assert report.counts == {'新增': 1, '更新': 1}
        assert {frozenset(pair[:2]) for pair in report.duplicates} == {frozenset(('A', 'B'))}


def test_generate_preserves_custom_import_headers_and_matches_configured_aliases(tmp_path):
    source = tmp_path / 'import.csv'
    snapshot = tmp_path / 'snapshot.csv'
    columns = Columns(code='编码', name='标签', aliases='别名', alias_separator=';')
    source.write_text('编码,标签,别名,备注\nNEW,创业,孵化;创业支持,自定义列\n', encoding='utf-8')
    snapshot.write_text('编码,标签,别名\nOLD,办公,孵化\n', encoding='utf-8')

    report = generate(source, snapshot, tmp_path, columns)

    assert report.counts == {'新增': 1}
    assert report.duplicates == [('NEW', 'OLD', '0.000', '孵化')]
    with (tmp_path / 'retry-import.csv').open(encoding='utf-8-sig', newline='') as output:
        with source.open(encoding='utf-8', newline='') as original:
            assert read_import(output, columns) == read_import(original, columns)
