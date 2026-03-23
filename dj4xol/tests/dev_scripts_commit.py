import importlib.machinery
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase


SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'dev_scripts' / 'commit'
LOADER = importlib.machinery.SourceFileLoader('dev_scripts_commit', str(SCRIPT_PATH))
SPEC = importlib.util.spec_from_loader('dev_scripts_commit', LOADER)
assert SPEC is not None
COMMIT_SCRIPT = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(COMMIT_SCRIPT)


class CommitScriptChangelogTest(TestCase):
    def test_update_changelog_rewrites_first_section_without_blank_lines(self):
        with TemporaryDirectory() as tmpdir:
            changelog_path = Path(tmpdir) / 'help_version_history.html'
            changelog_path.write_text(
                (
                    '<p>Intro</p>\n\n'
                    '        <h4><span class="env-label">v0.16.1</span></h4>\n\n'
                    '        <ul class="game-list">\n\n'
                    '            <li>Existing first item.</li>\n\n'
                    '            <li>Existing second item.</li>\n\n'
                    '        </ul>\n\n'
                    '        <h4><span class="env-label">v0.16.0</span></h4>\n\n'
                    '        <ul class="game-list">\n\n'
                    '            <li>Older item.</li>\n\n'
                    '        </ul>\n'
                ),
                encoding='utf-8',
            )

            COMMIT_SCRIPT.update_changelog(
                changelog_path=changelog_path,
                messages=['Newest item.'],
                version='0.16.1',
                start_new_version=False,
            )

            updated = changelog_path.read_text(encoding='utf-8')

        self.assertIn(
            '        <ul class="game-list">\n'
            '            <li>Newest item.</li>\n'
            '            <li>Existing first item.</li>\n'
            '            <li>Existing second item.</li>\n'
            '        </ul>',
            updated,
        )
        self.assertNotIn('<ul class="game-list">\n\n', updated)
        self.assertNotIn('</li>\n\n            <li>', updated)


class CommitScriptArgsTest(TestCase):
    def test_parse_args_defaults_to_staging(self):
        with patch('sys.argv', ['commit', 'Ship update']):
            args = COMMIT_SCRIPT.parse_args()
        self.assertFalse(args.skip_add)

    def test_parse_args_supports_skip_add_aliases(self):
        with patch('sys.argv', ['commit', '--skip-add', 'Ship update']):
            args_skip = COMMIT_SCRIPT.parse_args()
        with patch('sys.argv', ['commit', '--no-add', 'Ship update']):
            args_no = COMMIT_SCRIPT.parse_args()
        self.assertTrue(args_skip.skip_add)
        self.assertTrue(args_no.skip_add)
