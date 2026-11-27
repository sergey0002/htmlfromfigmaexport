"""Bounded PNG container checks tied to a previous snapshot, not provenance.

CRC and IHDR are checked without decompressing pixels. This is not a complete
PNG validator or evidence of correct image contents, origin or decoder safety.
"""
from __future__ import annotations
import struct
import zlib
from .snapshot import read_snapshot_file

MAX_BYTES=64*1024*1024
MAX_PIXELS=12_000_000
MAX_CHUNKS=10_000
_SIGNATURE=b'\x89PNG\r\n\x1a\n'
_DEPTHS={0:{1,2,4,8,16},2:{8,16},3:{1,2,4,8},4:{8,16},6:{8,16}}


def inspect(path,entry):
    raw=read_snapshot_file(path,entry,MAX_BYTES)
    if len(raw)<45 or raw[:8]!=_SIGNATURE: raise ValueError('Некорректная сигнатура PNG')
    view=memoryview(raw); pos=8; count=0; size=None; idat=False; idat_finished=False; data_bytes=0
    while pos<len(raw):
        count+=1
        if count>MAX_CHUNKS or len(raw)-pos<12: raise ValueError('Некорректная структура PNG')
        length=struct.unpack_from('>I',raw,pos)[0]; end=pos+12+length
        if end>len(raw): raise ValueError('Обрезанный chunk PNG')
        kind=raw[pos+4:pos+8]
        if any(not (65<=x<=90 or 97<=x<=122) for x in kind): raise ValueError('Некорректный тип chunk PNG')
        expected=struct.unpack_from('>I',raw,pos+8+length)[0]
        if zlib.crc32(view[pos+4:pos+8+length]) & 0xffffffff != expected: raise ValueError('Ошибка CRC chunk PNG')
        data=view[pos+8:pos+8+length]
        if count==1:
            if kind!=b'IHDR' or length!=13: raise ValueError('PNG должен начинаться с IHDR')
            width,height,depth,color,compression,filter_method,interlace=struct.unpack('>IIBBBBB',data)
            if (width<1 or height<1 or width>20000 or height>20000 or width*height>MAX_PIXELS or
                    color not in _DEPTHS or depth not in _DEPTHS[color] or
                    compression!=0 or filter_method!=0 or interlace not in (0,1)):
                raise ValueError('Недопустимые размеры или параметры IHDR PNG')
            size=[width,height]
        elif kind==b'IHDR': raise ValueError('Повторный IHDR PNG')
        elif kind==b'IDAT':
            if idat_finished: raise ValueError('Несмежные IDAT PNG')
            idat=True; data_bytes+=length
        elif kind==b'IEND':
            if length!=0 or not idat or data_bytes==0 or end!=len(raw): raise ValueError('Некорректное завершение PNG')
            return size
        elif kind in (b'acTL',b'fcTL',b'fdAT'): raise ValueError('Анимированный PNG не поддерживается')
        elif idat: idat_finished=True
        pos=end
    raise ValueError('PNG не содержит IEND')
