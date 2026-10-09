import importlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_regressions import document, field, encoded


def write_doc(path, text, binary=b'formula', extra=''):
    xml = document('<w:p><w:r><w:t>' + text + '</w:t></w:r>' + extra +
                   '<w:r><w:object><o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/>'
                   '</w:object></w:r></w:p>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', xml)
        z.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="embeddings/a.bin" Type="oleObject"/></Relationships>')
        z.writestr('word/embeddings/a.bin', binary)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.checker = importlib.import_module('check_manuscript_preservation')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.docx'
        self.final = Path(self.temp.name) / 'final.docx'
        write_doc(self.source, 'Original [1] text.')

    def test_citation_only_is_preserved(self):
        write_doc(self.final, 'Original [1] text.', extra=field('ADDIN EN.CITE ', encoded(1)))
        self.assertFalse(self.checker.compare(self.source, self.final)['issues'])

    def test_does_not_strip_original_numbered_text(self):
        write_doc(self.final, 'Original text.')
        self.assertTrue(self.checker.compare(self.source, self.final)['issues'])

    def test_formula_replaced_same_count_is_detected(self):
        write_doc(self.final, 'Original [1] text.', binary=b'other formula')
        self.assertTrue(self.checker.compare(self.source, self.final)['issues'])

    def test_formula_moved_same_paragraph_is_detected(self):
        write_doc(self.final, 'Original [1] text.')
        with zipfile.ZipFile(self.final) as z:
            parts = {name: z.read(name) for name in z.namelist()}
        xml = parts['word/document.xml'].decode()
        start = xml.index('<w:r><w:object>')
        end = xml.index('</w:object></w:r>', start) + len('</w:object></w:r>')
        obj = xml[start:end]
        xml = xml[:start] + xml[end:]
        parts['word/document.xml'] = xml.replace('<w:p>', '<w:p>' + obj, 1).encode()
        with zipfile.ZipFile(self.final, 'w') as z:
            for name, data in parts.items():
                z.writestr(name, data)
        report = self.checker.compare(self.source, self.final)
        self.assertEqual(report['source_objects'], report['final_objects'])
        self.assertTrue(report['issues'])

    def test_exact_authorized_change(self):
        write_doc(self.final, 'Corrected [1] text.')
        changes = [{'paragraph_index': 1, 'old': 'Original', 'new': 'Corrected', 'reason': 'Confirmed error'}]
        self.assertFalse(self.checker.compare(self.source, self.final, changes)['issues'])

    def test_ambiguous_authorized_change_fails(self):
        write_doc(self.source, 'A A')
        write_doc(self.final, 'B A')
        changes = [{'paragraph_index': 1, 'old': 'A', 'new': 'B', 'reason': 'Confirmed error'}]
        self.assertTrue(self.checker.compare(self.source, self.final, changes)['issues'])


if __name__ == '__main__':
    unittest.main()
