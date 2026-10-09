#!/usr/bin/env python3
"""Compare body text and anchored OLE/OMML content, allowing logged exact edits.

Paragraph indices are 1-based, including empty paragraphs and table paragraphs.
Only EndNote citation field content is excluded; ordinary [n] text is preserved.
This is a content check, not a replacement for Word layout/formatting review.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from inspect_docx_fields import W, NS, REFERENCE_HEADING_RE, field_command

R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
O = '{urn:schemas-microsoft-com:office:office}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def semantic(node):
    return [node.tag, sorted((k, v) for k, v in node.attrib.items() if 'rsid' not in k),
            node.text or '', [semantic(child) for child in node]]


def snapshot(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        rel_path = 'word/_rels/document.xml.rels'
        rels = ET.fromstring(archive.read(rel_path)) if rel_path in archive.namelist() else []
        targets = {node.get('Id'): node.get('Target') for node in rels if node.get('TargetMode') != 'External'}
        paragraphs, objects, issues = [], [], []
        stack = []
        for index, para in enumerate(root.findall('.//w:p', NS), 1):
            if para.findall('.//w:p', NS):
                issues.append(f'paragraph {index}: nested text-box paragraphs require separate review')
            raw = ''.join(node.text or '' for node in para.findall('.//w:t', NS))
            if REFERENCE_HEADING_RE.fullmatch(raw.strip()):
                break
            text = ''
            ordinal = 0
            # Recursion lets simple fields and OMML be handled without double counting.
            def walk(node):
                nonlocal text, ordinal
                if node.tag == W + 'fldSimple' and field_command(node.get(W + 'instr', '')) == 'EN.CITE':
                    return
                if node.tag == W + 'fldChar':
                    kind = node.get(W + 'fldCharType')
                    if kind == 'begin':
                        stack.append('')
                    elif kind == 'end' and stack:
                        stack.pop()
                    return
                if node.tag == W + 'instrText':
                    if stack:
                        stack[-1] += node.text or ''
                    return
                if (node.tag in {W + 't', W + 'tab', W + 'br', W + 'cr', O + 'OLEObject', M + 'oMath'}
                        and any(field_command(code) in {'EN.CITE', 'EN.CITE.DATA'} for code in stack)):
                    return
                if node.tag == W + 't':
                    text += node.text or ''
                elif node.tag in {W + 'tab', W + 'br', W + 'cr'}:
                    text += '\t' if node.tag == W + 'tab' else '\n'
                elif node.tag in {O + 'OLEObject', M + 'oMath'}:
                    ordinal += 1
                    if node.tag == O + 'OLEObject':
                        target = targets.get(node.get(R + 'id'))
                        part = posixpath.normpath(posixpath.join('word', target)) if target else ''
                        part = part.lstrip('/')
                        if not part or part not in archive.namelist():
                            issues.append(f'paragraph {index}: unresolved OLE relationship')
                            digest = ''
                        else:
                            digest = hashlib.sha256(archive.read(part)).hexdigest()
                    else:
                        digest = hashlib.sha256(json.dumps(semantic(node), ensure_ascii=False).encode()).hexdigest()
                    objects.append({'paragraph_index': index, 'ordinal': ordinal, 'prefix': text,
                                    'kind': node.tag.rsplit('}', 1)[-1], 'sha256': digest})
                    return
                for child in node:
                    walk(child)
            walk(para)
            paragraphs.append(text)
        return {'paragraphs': paragraphs, 'objects': objects, 'issues': issues}


def compare(source, final, changes=None):
    before, after = snapshot(source), snapshot(final)
    expected = deepcopy(before)
    issues = before['issues'] + after['issues']
    for change in changes or []:
        index = change.get('paragraph_index', 0) - 1
        old, new = change.get('old', ''), change.get('new', '')
        if (not 0 <= index < len(expected['paragraphs']) or not old or not change.get('reason')
                or expected['paragraphs'][index].count(old) != 1):
            issues.append(f'invalid or ambiguous authorized change: {change}')
            continue
        expected['paragraphs'][index] = expected['paragraphs'][index].replace(old, new, 1)
        for obj in expected['objects']:
            if obj['paragraph_index'] == index + 1:
                obj['prefix'] = obj['prefix'].replace(old, new, 1)
    if expected['paragraphs'] != after['paragraphs']:
        differing = [i for i, (a, b) in enumerate(zip(expected['paragraphs'], after['paragraphs']), 1) if a != b]
        issues.append(f'body text differs: source/final paragraphs {len(expected["paragraphs"])}/{len(after["paragraphs"])}; differing shared indices {differing}')
    if expected['objects'] != after['objects']:
        issues.append('OLE/OMML content or anchors differ; binary changes require review, not a claim of unchanged formulas')
    return {'source': str(source), 'final': str(final), 'source_paragraphs': len(before['paragraphs']),
            'final_paragraphs': len(after['paragraphs']), 'source_objects': len(before['objects']),
            'final_objects': len(after['objects']), 'authorized_changes': len(changes or []),
            'source_object_details': before['objects'], 'final_object_details': after['objects'], 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--final', type=Path, required=True)
    parser.add_argument('--changes', type=Path, help='JSON list: 1-based paragraph_index, old, new, reason; already authorized only')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    changes = json.loads(args.changes.read_text(encoding='utf-8-sig')) if args.changes else []
    report = compare(args.source, args.final, changes)
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        if args.report.resolve() in {args.source.resolve(), args.final.resolve()}:
            parser.error('report must not overwrite a manuscript')
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('_details')}, ensure_ascii=False, indent=2))
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
