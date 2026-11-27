"""Synthetic artifact transfer validation; not an authenticity or sandbox test."""
import hashlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('fixture_artifact_transfer',ROOT/'tests/fixtures/isolated-vite/artifact_transfer.py')
artifacts=importlib.util.module_from_spec(spec); spec.loader.exec_module(artifacts)


def png(color, size=(390,844)):
    with Image.new('RGB',size,color) as image:
        buf=io.BytesIO(); image.save(buf,format='PNG'); return buf.getvalue()


def frame(raw): return struct.pack('>I',len(raw))+raw


class SyntheticArtifactTests(unittest.TestCase):
    def test_verify_write_and_bind_bytes_without_authentication(self):
        first,second=png('red'),png('blue'); parsed=artifacts.parse_frames(frame(first)+frame(second))
        self.assertEqual([p['sha256'] for p in parsed],[hashlib.sha256(first).hexdigest(),hashlib.sha256(second).hexdigest()])
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            folder=Path(tmp)/'captures'; result=artifacts.write_artifacts(folder,parsed)
            self.assertEqual((folder/'reference.png').read_bytes(),first);self.assertEqual((folder/'candidate.png').read_bytes(),second)
            raw=(folder/'manifest.json').read_bytes(); self.assertEqual(result['manifest_sha256'],hashlib.sha256(raw).hexdigest())
            manifest=json.loads(raw); self.assertFalse(manifest['authenticated']);self.assertFalse(manifest['publication_eligible'])
            with self.assertRaises(ValueError): artifacts.write_artifacts(folder,parsed)

    def test_rejects_bad_frames_and_malformed_images(self):
        first,second=png('red'),png('blue'); bad=bytearray(first);bad[20]^=1
        cases=[b'',b'\x00\x00',struct.pack('>I',0),struct.pack('>I',artifacts.MAX_IMAGE+1),
               struct.pack('>I',len(first)+1)+first,frame(b'not a png')+frame(second),
               frame(bytes(bad))+frame(second),frame(first+b'trailing')+frame(second),
               frame(first)+frame(second)+b'extra',frame(first)+frame(first),
               frame(png('red',(1,1)))+frame(second),frame(first[:-5])+frame(second)]
        for value in cases:
            with self.subTest(value=value[:24]),self.assertRaises(ValueError): artifacts.parse_frames(value)

    def test_write_failure_preserves_partial_directory_without_manifest(self):
        parsed=artifacts.parse_frames(frame(png('red'))+frame(png('blue')))
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            folder=Path(tmp)/'captures'
            with patch.object(artifacts.os,'fsync',side_effect=OSError('injected')):
                with self.assertRaises(OSError): artifacts.write_artifacts(folder,parsed)
            self.assertTrue(folder.exists());self.assertFalse((folder/'manifest.json').exists())

if __name__=='__main__': unittest.main()
