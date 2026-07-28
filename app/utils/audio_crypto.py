"""Cifratura at-rest AES-256-CTR + HMAC-SHA256, streaming a chunk.

Formato file:
  MAGIC(4) | VERSION(1) | NONCE(16) | CIPHERTEXT... | HMAC(32)

La chiave (32 byte) arriva da env ``AUDIO_ENCRYPTION_KEY`` (hex 64 char o raw 32 byte).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import BinaryIO, Union

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"MNA2"
VERSION = b"\x01"
NONCE_LEN = 16
HMAC_LEN = 32
DEFAULT_CHUNK = 1024 * 1024

PathLike = Union[str, Path]


class AudioCryptoError(Exception):
    """Errore di cifratura/decifratura audio."""


def load_audio_key(raw: str | bytes | None) -> bytes:
    """Normalizza la chiave AES-256 da env."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise AudioCryptoError("AUDIO_ENCRYPTION_KEY non configurata")
    if isinstance(raw, bytes):
        key = raw
    else:
        text = raw.strip()
        if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
            key = bytes.fromhex(text)
        else:
            try:
                import base64

                key = base64.b64decode(text)
            except Exception as exc:  # noqa: BLE001
                raise AudioCryptoError("AUDIO_ENCRYPTION_KEY non valida") from exc
    if len(key) != 32:
        raise AudioCryptoError("AUDIO_ENCRYPTION_KEY deve essere di 32 byte (AES-256)")
    return key


def encrypt_file_streaming(
    src_path: PathLike,
    dst_path: PathLike,
    key: bytes,
    chunk_size: int = DEFAULT_CHUNK,
) -> None:
    """Cifra ``src_path`` su ``dst_path`` senza caricare l'intero file in RAM."""
    if len(key) != 32:
        raise AudioCryptoError("Chiave AES-256 non valida")
    nonce = os.urandom(NONCE_LEN)
    encryptor = Cipher(algorithms.AES(key), modes.CTR(nonce)).encryptor()
    mac = hmac.new(key, digestmod=hashlib.sha256)
    header = MAGIC + VERSION + nonce
    mac.update(header)

    src = Path(src_path)
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_suffix(dst.suffix + ".partial")

    try:
        with src.open("rb") as fin, tmp_dst.open("wb") as fout:
            fout.write(header)
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                ct = encryptor.update(chunk)
                mac.update(ct)
                fout.write(ct)
            ct_final = encryptor.finalize()
            if ct_final:
                mac.update(ct_final)
                fout.write(ct_final)
            fout.write(mac.digest())
        tmp_dst.replace(dst)
    except Exception:
        if tmp_dst.exists():
            tmp_dst.unlink(missing_ok=True)
        raise


def decrypt_file_streaming(
    src_path: PathLike,
    dst_path: PathLike,
    key: bytes,
    chunk_size: int = DEFAULT_CHUNK,
) -> None:
    """Decifra un file prodotto da :func:`encrypt_file_streaming`."""
    src = Path(src_path)
    size = src.stat().st_size
    min_size = len(MAGIC) + 1 + NONCE_LEN + HMAC_LEN
    if size < min_size:
        raise AudioCryptoError("File cifrato troppo corto o corrotto")

    ciphertext_len = size - min_size
    with src.open("rb") as fin:
        magic = fin.read(4)
        version = fin.read(1)
        nonce = fin.read(NONCE_LEN)
        if magic != MAGIC or version != VERSION:
            raise AudioCryptoError("Formato file cifrato non riconosciuto")

        mac = hmac.new(key, digestmod=hashlib.sha256)
        mac.update(magic + version + nonce)

        decryptor = Cipher(algorithms.AES(key), modes.CTR(nonce)).decryptor()
        dst = Path(dst_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.with_suffix(dst.suffix + ".partial")
        remaining = ciphertext_len
        try:
            with tmp_dst.open("wb") as fout:
                while remaining > 0:
                    to_read = min(chunk_size, remaining)
                    chunk = fin.read(to_read)
                    if len(chunk) != to_read:
                        raise AudioCryptoError("EOF prematuro nel ciphertext")
                    mac.update(chunk)
                    fout.write(decryptor.update(chunk))
                    remaining -= to_read
                pt_final = decryptor.finalize()
                if pt_final:
                    fout.write(pt_final)
            tag = fin.read(HMAC_LEN)
            if len(tag) != HMAC_LEN or not hmac.compare_digest(mac.digest(), tag):
                raise AudioCryptoError("HMAC non valido: file alterato o chiave errata")
            tmp_dst.replace(dst)
        except Exception:
            if tmp_dst.exists():
                tmp_dst.unlink(missing_ok=True)
            raise


def stream_to_file_with_hash(
    stream: BinaryIO,
    dest_path: PathLike,
    *,
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK,
) -> tuple[int, str]:
    """Scrive lo stream su disco a chunk, calcolando SHA-256 e imponendo un tetto size.

    Ritorna ``(dimensione_byte, checksum_hex)``.
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise AudioCryptoError(
                        f"File troppo grande: massimo {max_bytes} byte"
                    )
                hasher.update(chunk)
                out.write(chunk)
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise
    return size, hasher.hexdigest()
