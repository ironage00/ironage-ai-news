import ast
from pathlib import Path
import unittest


def load_function(name):
    source = (Path(__file__).resolve().parents[1] / 'news_engine.py').read_text(encoding='utf-8-sig')
    module = ast.parse(source)
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'news_engine.py', 'exec'), namespace)
    return namespace[name]


class NewsletterStatusTests(unittest.TestCase):
    def test_identifies_only_failed_units(self):
        failed = load_function('failed_newsletter_units')
        summary = {'failed': {'errors': ['이메일 발송 실패']},
                   'success': {'errors': []}, 'skipped': {'errors': []},
                   'other_error': {'errors': ['분析 결과 없음']}}
        self.assertEqual(failed(summary), ['failed'])

    def test_success_and_skipped_do_not_fail(self):
        failed = load_function('failed_newsletter_units')
        self.assertEqual(failed({'success': {'errors': []}, 'skipped': {}}), [])


if __name__ == '__main__':
    unittest.main()
