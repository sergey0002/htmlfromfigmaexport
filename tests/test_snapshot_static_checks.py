import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import snapshot_access
from tools.core import check_site
from tools.queue import check_manifest
from tools.snapshot import take_snapshot
from tools.snapshot_access import SnapshotAccess, MAX_TEXT_BYTES


def fixture(root):
    (root/'template').mkdir()
    (root/'template/header.php').write_text('<header>Header</header>')
    (root/'template/footer.php').write_text('<footer>Footer</footer>')
    html='''<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="style.css"></head><body><!-- HEADER:START --><header>Header</header><!-- HEADER:END --><main><img src="logo.svg" alt="logo"></main><!-- FOOTER:START --><footer>Footer</footer><!-- FOOTER:END --></body></html>'''
    (root/'index.html').write_text(html)
    (root/'style.css').write_text('body { background: url(asset.bin) }')
    (root/'logo.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (root/'asset.bin').write_bytes(b'data')
    manifest={'pages':[{'id':'home','output':'index.html','confirmation':'confirmed'}], 'discovery':{'status':'confirmed'}}
    return manifest,SnapshotAccess(root,take_snapshot(root,'delivery'))


class SnapshotStaticTests(unittest.TestCase):
    def test_legacy_and_snapshot_mode_have_matching_findings_on_stable_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest,access=fixture(root)
            legacy=check_manifest(root,manifest); bound=check_manifest(root,manifest,snapshot_access=access)
            for key in ('status','pages','issues','warnings','coverage'): self.assertEqual(legacy[key],bound[key],key)
            self.assertIsNotNone(legacy['fingerprint']); self.assertIsNone(bound['fingerprint'])

    def test_replaced_page_css_svg_asset_or_template_never_yields_success(self):
        for name in ('index.html','style.css','logo.svg','asset.bin','template/header.php','template/footer.php'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); manifest,access=fixture(root); target=root/name
                orig_read=snapshot_access.read_snapshot_file; orig_prefix=snapshot_access.read_snapshot_prefix
                changed=False
                def mutate_then(call,path,entry,limit):
                    nonlocal changed
                    if path==target and not changed:
                        changed=True; path.write_bytes(b'x'*entry['size'])
                    return call(path,entry,limit)
                with patch('tools.snapshot_access.read_snapshot_file',side_effect=lambda *args: mutate_then(orig_read,*args)), \
                     patch('tools.snapshot_access.read_snapshot_prefix',side_effect=lambda *args: mutate_then(orig_prefix,*args)):
                    try: result=check_manifest(root,manifest,snapshot_access=access)
                    except (OSError,ValueError): pass
                    else: self.assertEqual(result['status'],'FAIL',name)
                self.assertTrue(changed,name)

    def test_text_input_limit_is_fail_closed_without_changing_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); fixture(root); (root/'style.css').write_bytes(b' '* (MAX_TEXT_BYTES+1))
            access=SnapshotAccess(root,take_snapshot(root,'delivery'))
            with self.assertRaises(ValueError): check_site(root,snapshot_access=access)
            self.assertEqual(check_site(root)['status'],'INCOMPLETE')

    @unittest.skipUnless(hasattr(os,'mkfifo') and hasattr(os,'O_NONBLOCK'),'requires POSIX FIFO')
    def test_fifo_swap_before_candidate_open_cannot_block(self):
        script='''import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from tools.snapshot import take_snapshot
from tools.snapshot_access import SnapshotAccess
from tools.core import check_site
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); page=root/'index.html'; page.write_text('<html lang="en"><title>x</title></html>')
    access=SnapshotAccess(root,take_snapshot(root,'delivery'))
    original=os.open; done=False
    def swap(path,flags,*args,**kwargs):
        global done
        if Path(path)==page and not done:
            done=True; page.unlink(); os.mkfifo(page)
        return original(path,flags,*args,**kwargs)
    try:
        with patch('os.open',side_effect=swap): result=check_site(root,snapshot_access=access)
    except (OSError,ValueError): pass
    else: assert result['status']=='FAIL',result
    assert done
'''
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__': unittest.main()
