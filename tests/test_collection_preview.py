# -*- coding: utf-8 -*-
"""Проверка клавиатуры сбора фото: кнопка «Предпросмотр документа»."""
import ast
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot.py"


class CollectionPreviewTest(unittest.TestCase):
    def setUp(self):
        self.src = BOT.read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def _func(self, name):
        for node in self.tree.body:
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
                return node
        raise AssertionError(f"функция {name} не найдена")

    def test_ask_photo_has_doc_preview_button(self):
        fn = self._func("_ask_photo")
        seg = ast.get_source_segment(self.src, fn)
        # кнопка предпросмотра документа присутствует на шаге сбора фото
        self.assertIn("_doc_preview_button", seg)
        # а кнопки просмотра фото (collect:view) больше нет
        self.assertNotIn("collect:view", seg)

    def test_doc_preview_button_callback(self):
        fn = self._func("_doc_preview_button")
        seg = ast.get_source_segment(self.src, fn)
        self.assertIn("collect:doc", seg)

    def test_collect_doc_handler_exists(self):
        self.assertTrue(
            any(isinstance(n, ast.AsyncFunctionDef) and n.name == "collect_doc"
                for n in self.tree.body),
            "хендлер collect_doc отсутствует",
        )
        self.assertIn('F.data == "collect:doc"', self.src)

    def test_uses_register_preview_not_collection(self):
        self.assertIn("register_preview(dp", self.src)
        self.assertNotIn("register_collection_preview(", self.src)


if __name__ == "__main__":
    unittest.main()
