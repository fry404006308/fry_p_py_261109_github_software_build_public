"""One-job binary transport. The private key lives only in the target runner's temp directory."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import struct
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'FSB1'
CHUNK=2**20
PAD=padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=MAGIC)


def generate(private,public):
    key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    with os.fdopen(os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    with public.open('xb') as out:out.write(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))


def seal(src,dest,pub,expected):
    rsa_key=serialization.load_pem_public_key(pub.read_bytes())
    if not isinstance(rsa_key,rsa.RSAPublicKey) or rsa_key.key_size!=3072:raise ValueError('Unexpected runner key')
    key=secrets.token_bytes(32);nonce=secrets.token_bytes(12);wrapped=rsa_key.encrypt(key,PAD)
    stream=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();stream.authenticate_additional_data(bytes.fromhex(expected))
    checksum=hashlib.sha256()
    with src.open('rb') as f,dest.open('xb') as out:
        out.write(MAGIC+struct.pack('>H',len(wrapped))+wrapped+nonce)
        for block in iter(lambda:f.read(CHUNK),b''):
            checksum.update(block);out.write(stream.update(block))
        out.write(stream.finalize()+stream.tag)
    if checksum.hexdigest()!=expected:raise ValueError('Local input hash changed, do not upload')


def unseal(src,dest,private,expected,size):
    key=serialization.load_pem_private_key(private.read_bytes(),password=None)
    stage=dest.with_suffix(dest.suffix+'.unverified');checksum=hashlib.sha256()
    with src.open('rb') as inp:
        if inp.read(4)!=MAGIC or inp.read(2)!=struct.pack('>H',384):raise ValueError('Invalid envelope')
        symmetric=key.decrypt(inp.read(384),PAD);nonce=inp.read(12);offset=inp.tell()
        if src.stat().st_size!=offset+size+16:raise ValueError('Input length differs from manifest')
        inp.seek(-16,2);tag=inp.read(16);inp.seek(offset)
        stream=Cipher(algorithms.AES(symmetric),modes.GCM(nonce,tag)).decryptor();stream.authenticate_additional_data(bytes.fromhex(expected))
        with stage.open('xb') as out:
            remaining=size
            while remaining:
                b=inp.read(min(remaining,CHUNK))
                if not b:raise EOFError()
                data=stream.update(b);checksum.update(data);out.write(data);remaining-=len(b)
            out.write(stream.finalize())
    if checksum.hexdigest()!=expected:raise ValueError('Authenticated input differs from trusted manifest')
    os.replace(stage,dest)


if __name__=='__main__':
    import sys
    if sys.argv[1]=='key':generate(Path(sys.argv[2]),Path(sys.argv[3]))
    elif sys.argv[1]=='seal':seal(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5])
    else:raise SystemExit('Use the runner helper to verify and open a transport')
