"""Offline regression tests: python -m unittest discover -s tests -v."""
import base64
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_docx_fields as fields
import build_enw
import crossref_to_references as crossref
import enrich_references_crossref as enrich
import insert_temporary_citations as insert
from lxml import etree as ET


def document(content):
    return f'<w:document xmlns:w="{fields.NS["w"]}"><w:body>{content}</w:body></w:document>'


def field(code, payload="", result="[1]"):
    data = f'<w:fldData>{payload}</w:fldData>' if payload else ''
    return (f'<w:r><w:fldChar w:fldCharType="begin">{data}</w:fldChar></w:r>'
            f'<w:r><w:instrText>{code}</w:instrText></w:r>'
            f'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t>{result}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def encoded(n):
    return base64.b64encode(('<EndNote>' + '<Cite><RecNum>1</RecNum></Cite>' * n + '</EndNote>\0').encode()).decode()


class FieldTests(unittest.TestCase):
    def test_chinese_heading(self):
        self.assertEqual(fields.bibliography_entries(['正文', '参考文献', '1. A', '2. B']), ['1. A', '2. B'])

    def test_nested_native_data(self):
        child = field(' ADDIN EN.CITE.DATA ', encoded(3), '')
        content = field(' ADDIN EN.CITE ', encoded(3)).replace(
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>', child + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>', 1)
        self.assertEqual(fields.endnote_cite_group_sizes(document('<w:p>' + content + '</w:p>')), [3])

    def test_encoded_six_refs(self):
        self.assertEqual(fields.endnote_cite_group_sizes(document('<w:p>' + field('ADDIN EN.CITE ', encoded(6)) + '</w:p>')), [6])

    def test_malformed_payload_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.docx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('word/document.xml', document('<w:p>' + field('ADDIN EN.CITE ', 'not-base64') + '</w:p>'))
            self.assertTrue(fields.inspect(path)['issues'])

    def test_expected_references_without_mapping(self):
        xml = document('<w:p>' + field('ADDIN EN.CITE ', encoded(1)) + '</w:p>'
                       '<w:p><w:r><w:t>参考文献</w:t></w:r></w:p>'
                       '<w:p>' + field('ADDIN EN.REFLIST ', result='1. A') + '</w:p>')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.docx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('word/document.xml', xml)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fields.main([str(path), '--strict', '--expected-references', '1']), 0)

    def test_orphan_instruction_is_not_field(self):
        self.assertEqual(fields.endnote_cite_group_sizes(document('<w:p><w:r><w:instrText>ADDIN EN.CITE </w:instrText></w:r></w:p>')), [])


class MetadataTests(unittest.TestCase):
    def test_no_issue_sentinel_in_enw(self):
        self.assertNotIn('%N', build_enw.to_enw({'issue': 'not assigned'}))

    def test_enriched_enw_no_issue_sentinel(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.enw'
            enrich.write_enw([{'0': 'Journal Article', 'N': 'not assigned', '_order': ['N']}], path)
            self.assertNotIn('%N', path.read_text())

    def test_crossref_is_candidate(self):
        self.assertEqual(crossref.row_from_item({'title': ['Example']}, 1, set())['verified'], 'false')

    def test_formal_conference_type(self):
        self.assertEqual(crossref.reference_type('proceedings-article'), 'Conference Paper')


class InsertionTests(unittest.TestCase):
    def test_split_preserves_style_and_following_children(self):
        root = ET.fromstring(document('<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>ABC.</w:t><w:tab/><w:t>TAIL</w:t></w:r></w:p>'))
        p = root.find('.//' + fields.W + 'p')
        insert.insert_at_offset(p, 3, '{A, 2020 #1}')
        self.assertEqual(insert.paragraph_text(p), 'ABC {A, 2020 #1}.TAIL')
        tail = p[-1]
        self.assertIsNotNone(tail.find(fields.W + 'rPr/' + fields.W + 'b'))
        self.assertIsNotNone(tail.find(fields.W + 'tab'))


if __name__ == '__main__':
    unittest.main()
