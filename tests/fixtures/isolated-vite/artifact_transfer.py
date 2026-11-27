"""Synthetic screenshot transfer verifier. Not provenance or a security boundary."""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import zlib
from pathlib import Path

MAX_IMAGE=2_000_000
MAX_STREAM=2*MAX_IMAGE+8
SIZE=(390,844)


def parse_frames(data):
    from PIL import Image
    if not isinstance(data,bytes) or len(data)>MAX_STREAM:
        raise ValueError('synthetic artifact stream exceeds limit')
    offset=0; images=[]
    for _ in range(2):
        if len(data)-offset<4: raise ValueError('synthetic frame header truncated')
        size=struct.unpack_from('>I',data,offset)[0]; offset+=4
        if size<8 or size>MAX_IMAGE or len(data)-offset<size:
            raise ValueError('synthetic frame length invalid or truncated')
        blob=data[offset:offset+size]; offset+=size
        if not blob.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('synthetic frame is not PNG')
        pos=8; chunks=0; data_seen=False; ended=False
        while pos<len(blob):
            if len(blob)-pos<12: raise ValueError('synthetic PNG chunk truncated')
            length=struct.unpack_from('>I',blob,pos)[0]; kind=blob[pos+4:pos+8]
            if length>MAX_IMAGE or pos+12+length>len(blob): raise ValueError('synthetic PNG chunk length invalid')
            body=blob[pos+8:pos+8+length]; crc=struct.unpack_from('>I',blob,pos+8+length)[0]
            if zlib.crc32(kind+body)&0xffffffff!=crc: raise ValueError('synthetic PNG chunk CRC mismatch')
            chunks+=1
            if chunks>1000 or (chunks==1 and (kind!=b'IHDR' or length!=13)):
                raise ValueError('synthetic PNG structure invalid')
            if kind==b'IDAT': data_seen=True
            if kind in (b'acTL',b'fcTL',b'fdAT'): raise ValueError('animated PNG unsupported')
            pos+=12+length
            if kind==b'IEND':
                if length or not data_seen or pos!=len(blob): raise ValueError('synthetic PNG trailing or missing data')
                ended=True;break
        if not ended: raise ValueError('synthetic PNG has no IEND')
        try:
            with Image.open(io.BytesIO(blob)) as image:
                if image.format!='PNG' or image.size!=SIZE: raise ValueError('synthetic PNG format or dimensions invalid')
                image.verify()
            with Image.open(io.BytesIO(blob)) as image:
                if image.format!='PNG' or image.size!=SIZE: raise ValueError('synthetic PNG dimensions changed')
                image.load()
        except (OSError,ValueError,SyntaxError) as exc:
            raise ValueError('synthetic PNG failed decoding') from exc
        images.append({'bytes':blob,'sha256':hashlib.sha256(blob).hexdigest(),'size':len(blob)})
    if offset!=len(data): raise ValueError('unexpected trailing synthetic artifact frames')
    if images[0]['sha256']==images[1]['sha256']: raise ValueError('synthetic fixture captures should differ')
    return images


def write_artifacts(folder, images):
    folder=Path(folder)
    if folder.exists() or len(images)!=2: raise ValueError('new synthetic artifact folder required')
    folder.mkdir(mode=0o700)
    entries=[]
    for index,item in enumerate(images):
        name=('reference.png','candidate.png')[index]; path=folder/name
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
        fd=os.open(path,flags,0o600)
        with os.fdopen(fd,'wb') as out:
            out.write(item['bytes']);out.flush();os.fsync(out.fileno())
        # Verify the bytes actually persisted, not merely the sender's claim.
        stored=path.read_bytes()
        if len(stored)!=item['size'] or hashlib.sha256(stored).hexdigest()!=item['sha256']:
            raise ValueError('synthetic artifact changed during persistence')
        entries.append({'name':name,'size':len(stored),'sha256':item['sha256'],'width':SIZE[0],'height':SIZE[1]})
    manifest={'version':1,'kind':'synthetic-browser-captures','artifacts':entries,
              'authenticated':False,'isolated_provenance':False,'publication_eligible':False}
    raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode('utf8')
    fd=os.open(folder/'manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as out: out.write(raw);out.flush();os.fsync(out.fileno())
    for directory in (folder,folder.parent):
        fd=os.open(directory,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
        try: os.fsync(fd)
        finally: os.close(fd)
    return {'manifest_sha256':hashlib.sha256(raw).hexdigest(),'artifacts':entries,
            'authenticated':False,'publication_eligible':False}
