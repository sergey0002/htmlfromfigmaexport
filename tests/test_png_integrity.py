import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from tools import png_integrity
from tools.snapshot import take_snapshot


def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)


def image(width=2,height=3,payload=None):
    header=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    data=zlib.compress(b'\0'+b'\0'*width*3)*height if payload is None else payload
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',data)+chunk(b'IEND',b'')


class PngContainerTests(unittest.TestCase):
    def check(self,blob):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'image.png'; path.write_bytes(blob)
            entry=take_snapshot(root,'delivery')['entries'][0]
            return png_integrity.inspect(path,entry)

    def test_framing_and_dimensions_checked_without_claiming_pixel_validity(self):
        self.assertEqual(self.check(image()),[2,3])
        # Framing is not a decoder: valid CRCs on bogus compressed data can pass.
        self.assertEqual(self.check(image(payload=b'not compressed pixels')),[2,3])

    def test_rejects_corruption_truncation_trailing_and_oversize_dimensions(self):
        raw=image(); corrupt=bytearray(raw); corrupt[20]^=1
        for value in (b'not PNG',bytes(corrupt),raw[:-5],raw+b'extra',image(20000,20000,b'x'),image(0,1),
                      raw[:33]+chunk(b'acTL',b'\0'*8)+raw[33:]):
            with self.subTest(size=len(value)),self.assertRaises(ValueError): self.check(value)

    def test_snapshot_mismatch_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'a'; path.write_bytes(image())
            entry=take_snapshot(root,'delivery')['entries'][0]; path.write_bytes(image(payload=b'changed'))
            with self.assertRaises(ValueError): png_integrity.inspect(path,entry)

if __name__=='__main__': unittest.main()
