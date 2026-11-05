"""DOCX-only output, including old PDF buttons and failed uploads."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

SOURCE = (Path(__file__).resolve().parents[1] / 'bot.py').read_text()
TREE = ast.parse(SOURCE)


def load_function(name, namespace):
    node = next(n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<bot-test>', 'exec'), namespace)
    return namespace[name]


class DocxOnlyTests(unittest.IsolatedAsyncioTestCase):
    def test_no_pdf_button_or_converter(self):
        kb = load_function('_preview_kb', {'InlineKeyboardMarkup': InlineKeyboardMarkup, 'InlineKeyboardButton': InlineKeyboardButton})()
        callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertNotIn('prev:pdf', callbacks)
        self.assertIn('prev:word', callbacks)
        self.assertNotIn('_convert_to_pdf', SOURCE)
        self.assertNotIn('_pdf_slots', SOURCE)
        self.assertNotIn('libreoffice', (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text().lower())

    async def test_old_button_sends_word(self):
        word = AsyncMock()
        handler = load_function('legacy_document', {'CallbackQuery': object, 'FSMContext': object, 'prev_word': word})
        await handler('callback', 'state')
        word.assert_awaited_once_with('callback', 'state')

    async def test_draft_docx_and_cleanup_even_on_upload_error(self):
        import os
        for fail in (False, True):
            with self.subTest(upload_fails=fail), tempfile.TemporaryDirectory() as directory:
                draft = Path(directory) / 'draft.docx'
                draft.write_bytes(b'test')
                build = AsyncMock(return_value=str(draft))
                cb, state = AsyncMock(), AsyncMock()
                state.get_data.return_value = {'slots': [{'id': 'one'}], 'containers': ['container'], 'photos': {}}
                if fail:
                    cb.message.answer_document.side_effect = RuntimeError('upload failed')
                handler = load_function('collect_doc', {'CallbackQuery': object, 'FSMContext': object, '_build_doc': build, 'FSInputFile': FSInputFile, 'os': os})
                if fail:
                    with self.assertRaises(RuntimeError):
                        await handler(cb, state)
                else:
                    await handler(cb, state)
                sent = cb.message.answer_document.call_args.args[0]
                self.assertEqual(str(sent.path), str(draft))
                self.assertFalse(draft.exists())
                build.assert_awaited_once_with(state, cache=False)
