"""Generate an HTML tag-import report and an editable source-shaped CSV."""

import csv
import html
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations, product
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class Columns:
    code: str = 'code'
    name: str = 'name'
    aliases: str = 'aliases'
    alias_separator: str = '|'


def read_import(source: TextIO, columns: Columns = Columns()):
    reader = csv.DictReader(source)
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not {columns.code, columns.name, columns.aliases} <= set(fields):
        raise ValueError('CSV headers must uniquely include the configured code, name and alias columns.')
    rows = []
    for number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'CSV record {number} has a different column count from the header.')
        rows.append(row)
    return fields, rows


def write_retry_csv(destination: TextIO, fields: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    writer = csv.DictWriter(destination, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


def normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def alias_set(text: str, separator: str) -> set[str]:
    return {alias for part in text.split(separator) if (alias := normalized(part))}


@dataclass(frozen=True)
class Report:
    total: int
    counts: dict[str, int]
    errors: list[tuple]
    conflicts: list[tuple]
    duplicates: list[tuple]


def validate_import(rows: list[dict[str, str]], existing: list[dict[str, str]], columns: Columns = Columns()) -> Report:
    c = columns
    database = {normalized(row[c.code]): row for row in existing}
    if len(database) != len(existing) or '' in database:
        raise ValueError('The existing snapshot must have unique nonempty codes.')
    counts: Counter = Counter()
    errors, conflicts, valid = [], [], []
    input_codes = Counter(normalized(row[c.code]) for row in rows)
    for number, row in enumerate(rows, 2):
        code = normalized(row[c.code])
        missing = [field for field in (c.code, c.name) if not normalized(row[field])]
        if missing:
            errors.extend((number, field, '必填字段为空') for field in missing)
            counts['错误'] += 1
            continue
        if input_codes[code] > 1:
            conflicts.append((number, row[c.code], '同一批次出现相同编码', database.get(code, {}).get(c.name, ''), row[c.name]))
            counts['冲突'] += 1
            continue
        original = database.get(code)
        if original is None:
            counts['新增'] += 1
        elif any(original.get(field) != row[field] for field in (c.name, c.aliases)):
            counts['更新'] += 1
        else:
            counts['无变化'] += 1
        valid.append(row)

    duplicates = []
    # Compare the proposed value of a tag that this import updates, rather
    # than comparing both the proposed value and its superseded snapshot.
    proposed_codes = {normalized(row[c.code]) for row in valid}
    unchanged_snapshot = [row for row in existing if normalized(row[c.code]) not in proposed_codes]
    for pairs in (product(valid, unchanged_snapshot), combinations(valid, 2)):
        for left, right in pairs:
            common = sorted(alias_set(left[c.aliases], c.alias_separator) & alias_set(right[c.aliases], c.alias_separator))
            score = SequenceMatcher(None, normalized(left[c.name]), normalized(right[c.name]), autojunk=False).ratio()
            if score > 0.85 or common:
                duplicates.append((left[c.code], right[c.code], f'{score:.3f}', '、'.join(common)))
    return Report(len(rows), dict(counts), errors, conflicts, duplicates)


def render_html(report: Report) -> str:
    def table(labels, rows):
        head = ''.join(f'<th scope="col">{html.escape(label)}</th>' for label in labels)
        body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in row) + '</tr>' for row in rows)
        if not body:
            body = f'<tr><td colspan="{len(labels)}">无记录</td></tr>'
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    summary = [('总行数', report.total)] + [(label, report.counts.get(label, 0)) for label in ('新增', '更新', '冲突', '错误', '无变化')]
    sections = [
        ('汇总', table(('指标', '记录数'), summary)),
        ('错误', table(('源记录号', '字段', '原因'), report.errors)),
        ('冲突', table(('源记录号', '编码', '原因', '现有名称', '导入名称'), report.conflicts)),
        ('疑似重复', table(('导入编码', '候选编码', '名称相似度', '共同别名'), report.duplicates)),
    ]
    body = ''.join(f'<section><h2>{title}</h2>{content}</section>' for title, content in sections)
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<title>字典导入校验报告</title><style>body{font:16px system-ui,sans-serif;max-width:64rem;margin:2rem auto;padding:0 1rem;color:#17324a}'
            'table{border-collapse:collapse;width:100%;margin:.5rem 0 1.75rem}th,td{padding:.55rem;text-align:left;border-bottom:1px solid #d2dfeb}'
            'th{background:#ecf4fa}h1{font-size:1.6rem}h2{font-size:1.12rem}</style>'
            f'<main><h1>字典导入校验报告</h1>{body}</main></html>')


def generate(import_path: Path, snapshot_path: Path, out_dir: Path, columns: Columns = Columns()) -> Report:
    with import_path.open(encoding='utf-8-sig', newline='') as source:
        fields, rows = read_import(source, columns)
    with snapshot_path.open(encoding='utf-8-sig', newline='') as source:
        _, existing = read_import(source, columns)
    report = validate_import(rows, existing, columns)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'import-report.html').write_text(render_html(report), encoding='utf-8')
    with (out_dir / 'retry-import.csv').open('w', encoding='utf-8-sig', newline='') as output:
        write_retry_csv(output, fields, rows)
    return report


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('import_file', type=Path)
    parser.add_argument('snapshot_file', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    generate(args.import_file, args.snapshot_file, args.output_directory)
