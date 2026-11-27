"""Smoke-test the active docs against the actual read-only CLI help."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ACTIVE=[ROOT/'AGENTS.md',ROOT/'CLAUDE.md',*(ROOT/'.agents/skills').glob('*/SKILL.md'),
        *(ROOT/'.doc'/name for name in ('README.md','tools.md','agent-workflow.md','queue-md.md','runner-spike.md'))]


class DocumentationContractTests(unittest.TestCase):
    def test_active_local_markdown_links_exist(self):
        for path in ACTIVE:
            text=path.read_text(encoding='utf8')
            for link in re.findall(r'\]\(([^)]+)\)',text):
                local=link.split('#',1)[0]
                if local and not local.startswith(('https:', 'http:', 'mailto:')):
                    with self.subTest(file=path.name,link=link): self.assertTrue((path.parent/local).exists())

    def test_documented_commands_and_safety_flags_exist(self):
        commands={'runner-profiles':[], 'runner-synthetic':['--allow-fixture-registry-network','--timeout'], 'discover':['--source','--include-source-text'],
                  'coverage':['--site'], 'template-tokens':['--site','--page','--block','--offset','--limit'], 'materialize':['--selection','--output','--permission-profile','--acknowledge-world-readable'],
                  'browser-audit-md':['--reference-url','--site'],
                  'publish-plan':['--delivery-record','--target','--report'],
                  'publish-apply':['--plan','--sha256','--acknowledge-offline-writers'],
                  'publication-inspect':['--id'],
                  'publication-restore':['--id','--expected-target-sha256','--expect-target-absent','--clear-stale-lock'],
                  'manual-attest':['--actor','--limitations'],
                  'reference-materialize':['--selection','--output'], 'reference-inspect':['--file','--sha256'],
                  'pnpm-lock-inventory':['--source','--project'],
                  'pnpm-lock-cache':['--source','--project','--allow-registry-network','--selected-platform'],
                  'pnpm-tree-prepare':['--source','--project','--output'],
                  'pnpm-tree-inspect':['--source','--file','--sha256'],
                  'npm-lock-plan':['--source','--project'],
                  'npm-lock-prepare':['--source','--project','--output','--allow-registry-network'],
                  'npm-lock-inspect':['--source','--file','--sha256'],
                  'browser-audit-static-md':['--reference-record','--reference-sha256','--acknowledge-browser-code'],
                  'run-seal':['--audit','--summary-sha256'], 'run-inspect':['--file','--sha256'],
                  'readiness':['--run-record','--run-sha256','--manual-record','--manual-sha256'],
                  'queue-md migrate-apply':['--expected-manifest-sha256','--expected-markdown-sha256','--acknowledge-offline-writers']}
        for cmd,flags in commands.items():
            with self.subTest(command=cmd):
                out=subprocess.run([sys.executable,'-m','tools.cli',*cmd.split(),'--help'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
                for flag in flags: self.assertIn(flag,out)

    def test_historical_docs_do_not_claim_previous_report_is_current(self):
        for path in [*(ROOT/'.doc').glob('0*.md'),ROOT/'.doc/planarena.md']:
            with self.subTest(file=path.name):
                text=path.read_text(encoding='utf8')[:1500]
                self.assertIn('Исторический материал',text)
                self.assertIn('другому экспорту',text)
                self.assertNotIn('Для текущего `vanilla/` см.',text)

if __name__=='__main__': unittest.main()
