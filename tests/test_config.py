import unittest
import textwrap
import io
from unitd.config import Parser, ParseError

def test_input(s):
    return io.StringIO(textwrap.dedent(s.lstrip("\n")))

def test_parse(s):
    return list(Parser(test_input(s)).parse())


class TestParser(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(test_parse(""), [])
        self.assertEqual(test_parse("\n\n"), [])
        self.assertEqual(test_parse("\n#comment\n"), [])

        with self.assertRaises(ParseError):
            test_parse("a=1")

        l = test_parse("""
        [test]
        a=1
        a=2
        [test1]
        a=3
        """)
        self.assertEqual(l, [
            ("test", "a", "1"),
            ("test", "a", "2"),
            ("test1", "a", "3"),
        ])






