import unittest

from agentd.strings import clip, clip_middle, isolate, pango, printable, width


class ClipTest(unittest.TestCase):
    def test_prose_keeps_the_head_and_cuts_at_a_word(self):
        self.assertEqual(clip("Montar el rice del PC nuevo", 16), "Montar el rice…")
        self.assertEqual(clip("Arreglar el login con passkeys", 16), "Arreglar el…")

    def test_a_word_ending_exactly_at_the_cut_is_kept(self):
        self.assertEqual(clip("Arreglar el login con passkeys", 12), "Arreglar el…")

    def test_one_long_word_is_cut_hard(self):
        self.assertEqual(clip("supercalifragilistico", 8), "superca…")

    def test_short_text_is_untouched(self):
        self.assertEqual(clip("  corto  ", 16), "corto")

    def test_names_keep_both_ends(self):
        self.assertEqual(clip_middle("radio-web.github.io", 9), "radi…b.io")
        self.assertEqual(clip_middle("inventario-de-subredes", 11), "inven…redes")


class WideTextTest(unittest.TestCase):
    def test_width_counts_cjk_double_and_combining_marks_zero(self):
        self.assertEqual(width("ab漢字e\u0301"), 7)

    def test_clips_measure_cells_not_code_points(self):
        self.assertEqual(clip("漢字テスト漢字テスト", 7), "漢字テ…")
        self.assertEqual(clip_middle("漢字テスト漢字", 7), "漢…字")


class SafeTextTest(unittest.TestCase):
    def test_isolate_keeps_a_right_to_left_label_from_reordering_its_neighbours(self):
        self.assertEqual(isolate("שלום"), "\u2068שלום\u2069")

    def test_pango_escapes_and_keeps_private_use_glyphs(self):
        self.assertEqual(pango("a & <b> \U000f1719​"), "a &amp; &lt;b&gt; \U000f1719")

    def test_printable_is_one_line(self):
        self.assertEqual(printable("a\nb c\x00 d"), "a b c d")


if __name__ == "__main__":
    unittest.main()
