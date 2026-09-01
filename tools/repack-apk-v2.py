#!/usr/bin/env python3
"""Repack an APK with compressed native libraries and an APK Signature v2.

This is an emergency/debug packaging utility for SideQuest sideload builds.
It deliberately generates a fresh self-signed debug certificate. It is not a
replacement for a protected release keystore.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
APK_SIGNATURE_SCHEME_V2_ID = 0x7109871A
RSA_PKCS1_SHA256_ID = 0x0103
CHUNK_SIZE = 1024 * 1024


def lp32(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload


def read_lp32(payload: bytes, offset: int) -> tuple[bytes, int]:
    size = struct.unpack_from("<I", payload, offset)[0]
    start = offset + 4
    end = start + size
    if end > len(payload):
        raise ValueError("Length-prefixed value exceeds its container")
    return payload[start:end], end


def find_eocd(apk: bytes) -> int:
    # ZIP comments are at most 65535 bytes, plus the 22-byte EOCD record.
    start = max(0, len(apk) - 65557)
    offset = apk.rfind(b"PK\x05\x06", start)
    if offset < 0:
        raise ValueError("ZIP EOCD record not found")
    comment_size = struct.unpack_from("<H", apk, offset + 20)[0]
    if offset + 22 + comment_size != len(apk):
        raise ValueError("Malformed ZIP EOCD/comment length")
    return offset


def decode_len8(data: bytes, offset: int) -> tuple[int, int]:
    value = data[offset]
    offset += 1
    if value & 0x80:
        value = ((value & 0x7F) << 8) | data[offset]
        offset += 1
    return value, offset


def decode_len16(data: bytes, offset: int) -> tuple[int, int]:
    value = struct.unpack_from("<H", data, offset)[0]
    offset += 2
    if value & 0x8000:
        value = ((value & 0x7FFF) << 16) | struct.unpack_from(
            "<H", data, offset
        )[0]
        offset += 2
    return value, offset


def parse_string_pool(
    data: bytes, chunk_offset: int
) -> tuple[list[str], list[tuple[int, int, bool]], int]:
    header_size = struct.unpack_from("<H", data, chunk_offset + 2)[0]
    chunk_size = struct.unpack_from("<I", data, chunk_offset + 4)[0]
    string_count = struct.unpack_from("<I", data, chunk_offset + 8)[0]
    flags = struct.unpack_from("<I", data, chunk_offset + 16)[0]
    strings_start = struct.unpack_from("<I", data, chunk_offset + 20)[0]
    utf8 = bool(flags & 0x100)
    strings: list[str] = []
    locations: list[tuple[int, int, bool]] = []
    base = chunk_offset + strings_start

    for index in range(string_count):
        relative = struct.unpack_from(
            "<I", data, chunk_offset + header_size + index * 4
        )[0]
        cursor = base + relative
        if utf8:
            _, cursor = decode_len8(data, cursor)
            byte_length, cursor = decode_len8(data, cursor)
            raw = data[cursor : cursor + byte_length]
            text = raw.decode("utf-8")
            locations.append((cursor, byte_length, True))
        else:
            char_length, cursor = decode_len16(data, cursor)
            byte_length = char_length * 2
            raw = data[cursor : cursor + byte_length]
            text = raw.decode("utf-16le")
            locations.append((cursor, byte_length, False))
        strings.append(text)

    return strings, locations, chunk_size


def patch_manifest(manifest: bytes) -> bytes:
    """Set extractNativeLibs=true, versionCode=125 and a same-size name."""
    data = bytearray(manifest)
    strings: list[str] = []
    locations: list[tuple[int, int, bool]] = []
    offset = 8
    found_extract = False
    found_version_code = False

    while offset < len(data):
        chunk_type = struct.unpack_from("<H", data, offset)[0]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        if chunk_size < 8 or offset + chunk_size > len(data):
            raise ValueError("Malformed binary AndroidManifest.xml")

        if chunk_type == 0x0001:
            strings, locations, _ = parse_string_pool(bytes(data), offset)
        elif chunk_type == 0x0102 and strings:
            element_name_index = struct.unpack_from("<I", data, offset + 20)[0]
            element_name = strings[element_name_index]
            attribute_start = struct.unpack_from("<H", data, offset + 24)[0]
            attribute_size = struct.unpack_from("<H", data, offset + 26)[0]
            attribute_count = struct.unpack_from("<H", data, offset + 28)[0]
            cursor = offset + 16 + attribute_start

            for index in range(attribute_count):
                attribute = cursor + index * attribute_size
                name_index = struct.unpack_from("<I", data, attribute + 4)[0]
                name = strings[name_index]
                value_type = data[attribute + 15]

                if element_name == "application" and name == "extractNativeLibs":
                    if value_type != 0x12:
                        raise ValueError("extractNativeLibs is not a boolean")
                    struct.pack_into("<I", data, attribute + 16, 0xFFFFFFFF)
                    found_extract = True

                if element_name == "manifest" and name == "versionCode":
                    if value_type not in (0x10, 0x11):
                        raise ValueError("versionCode is not an integer")
                    struct.pack_into("<I", data, attribute + 16, 125)
                    found_version_code = True

        offset += chunk_size

    old_name = "0.9.30-exp35-ime-thumb-zoom"
    new_name = "0.9.30-exp37-aligned-apk-v2"
    if len(old_name) != len(new_name):
        raise AssertionError("Replacement versionName must have equal length")
    try:
        string_index = strings.index(old_name)
    except ValueError as exc:
        raise ValueError("Expected Exp35 versionName missing from manifest") from exc
    string_offset, byte_length, utf8 = locations[string_index]
    old_encoded = old_name.encode("utf-8" if utf8 else "utf-16le")
    new_encoded = new_name.encode("utf-8" if utf8 else "utf-16le")
    if byte_length != len(old_encoded) or len(new_encoded) != byte_length:
        raise ValueError("Unexpected versionName string encoding")
    data[string_offset : string_offset + byte_length] = new_encoded

    if not found_extract:
        raise ValueError("extractNativeLibs attribute missing from manifest")
    if not found_version_code:
        raise ValueError("versionCode attribute missing from manifest")
    return bytes(data)


def clone_zip_info(source: ZipInfo) -> ZipInfo:
    target = ZipInfo(source.filename, source.date_time)
    target.comment = source.comment
    target.extra = source.extra
    target.create_system = source.create_system
    target.create_version = source.create_version
    target.extract_version = source.extract_version
    target.flag_bits = source.flag_bits & ~0x08
    target.internal_attr = source.internal_attr
    target.external_attr = source.external_attr
    target.volume = source.volume
    return target


def repack_unsigned(source: Path, output: Path) -> None:
    with ZipFile(source, "r") as incoming, ZipFile(
        output, "w", allowZip64=False
    ) as outgoing:
        outgoing.comment = incoming.comment
        for entry in incoming.infolist():
            upper = entry.filename.upper()
            if upper.startswith("META-INF/") and upper.endswith(
                (".RSA", ".DSA", ".EC", ".SF", "MANIFEST.MF")
            ):
                continue
            payload = incoming.read(entry)
            if entry.filename == "AndroidManifest.xml":
                payload = patch_manifest(payload)
            target = clone_zip_info(entry)
            if entry.filename.startswith("lib/") and entry.filename.endswith(".so"):
                target.compress_type = ZIP_DEFLATED
                target.extra = b""
            elif entry.filename == "resources.arsc":
                # Android 11+ requires this entry to be STORED and its payload
                # to begin on a 4-byte boundary.  Add a harmless ZIP extra
                # field whose total size supplies the required padding.
                target.compress_type = ZIP_STORED
                target.extra = b""
                filename_size = len(target.filename.encode("utf-8"))
                data_offset = outgoing.fp.tell() + 30 + filename_size
                padding_size = (-data_offset) % 4
                if padding_size:
                    target.extra = (
                        struct.pack("<HH", 0xCAFE, padding_size)
                        + b"\x00" * padding_size
                    )
            else:
                target.compress_type = entry.compress_type
            outgoing.writestr(target, payload, compresslevel=9)


def chunked_content_digest(sections: list[bytes]) -> bytes:
    chunk_digests: list[bytes] = []
    for section in sections:
        for offset in range(0, len(section), CHUNK_SIZE):
            chunk = section[offset : offset + CHUNK_SIZE]
            prefix = b"\xA5" + struct.pack("<I", len(chunk))
            chunk_digests.append(hashlib.sha256(prefix + chunk).digest())
    top = b"\x5A" + struct.pack("<I", len(chunk_digests))
    return hashlib.sha256(top + b"".join(chunk_digests)).digest()


def generate_debug_identity() -> tuple[rsa.RSAPrivateKey, bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "GeoGebraForQuest Exp36 Debug"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "GeoGebraForQuest"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
        ]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .sign(private_key, hashes.SHA256())
    )
    certificate_der = certificate.public_bytes(serialization.Encoding.DER)
    public_key_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, certificate_der, public_key_der


def make_v2_signing_block(unsigned_apk: bytes) -> tuple[bytes, str]:
    eocd_offset = find_eocd(unsigned_apk)
    central_directory_offset = struct.unpack_from(
        "<I", unsigned_apk, eocd_offset + 16
    )[0]
    if central_directory_offset >= eocd_offset:
        raise ValueError("Invalid central directory offset")
    content_digest = chunked_content_digest(
        [
            unsigned_apk[:central_directory_offset],
            unsigned_apk[central_directory_offset:eocd_offset],
            unsigned_apk[eocd_offset:],
        ]
    )

    private_key, certificate_der, public_key_der = generate_debug_identity()
    digest_record = lp32(
        struct.pack("<I", RSA_PKCS1_SHA256_ID) + lp32(content_digest)
    )
    signed_data = lp32(digest_record) + lp32(lp32(certificate_der)) + lp32(b"")
    signature = private_key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
    signature_record = lp32(
        struct.pack("<I", RSA_PKCS1_SHA256_ID) + lp32(signature)
    )
    signer = lp32(signed_data) + lp32(signature_record) + lp32(public_key_der)
    v2_value = lp32(lp32(signer))
    pair = (
        struct.pack("<Q", 4 + len(v2_value))
        + struct.pack("<I", APK_SIGNATURE_SCHEME_V2_ID)
        + v2_value
    )
    block_size = len(pair) + 24
    signing_block = (
        struct.pack("<Q", block_size)
        + pair
        + struct.pack("<Q", block_size)
        + APK_SIG_BLOCK_MAGIC
    )
    fingerprint = hashlib.sha256(certificate_der).hexdigest()
    return signing_block, fingerprint


def sign_apk(unsigned_path: Path, output_path: Path) -> str:
    unsigned = unsigned_path.read_bytes()
    eocd_offset = find_eocd(unsigned)
    central_directory_offset = struct.unpack_from("<I", unsigned, eocd_offset + 16)[0]
    signing_block, fingerprint = make_v2_signing_block(unsigned)
    patched_eocd = bytearray(unsigned[eocd_offset:])
    struct.pack_into(
        "<I",
        patched_eocd,
        16,
        central_directory_offset + len(signing_block),
    )
    output = (
        unsigned[:central_directory_offset]
        + signing_block
        + unsigned[central_directory_offset:eocd_offset]
        + patched_eocd
    )
    output_path.write_bytes(output)
    return fingerprint


def parse_v2_pair(apk: bytes) -> tuple[int, int, bytes]:
    magic_offset = apk.rfind(APK_SIG_BLOCK_MAGIC)
    if magic_offset < 8:
        raise ValueError("APK Signature Block missing")
    block_end = magic_offset + len(APK_SIG_BLOCK_MAGIC)
    block_size = struct.unpack_from("<Q", apk, magic_offset - 8)[0]
    block_start = block_end - (block_size + 8)
    if struct.unpack_from("<Q", apk, block_start)[0] != block_size:
        raise ValueError("APK Signature Block size mismatch")
    cursor = block_start + 8
    pairs_end = magic_offset - 8
    while cursor < pairs_end:
        pair_size = struct.unpack_from("<Q", apk, cursor)[0]
        cursor += 8
        pair_id = struct.unpack_from("<I", apk, cursor)[0]
        cursor += 4
        value = apk[cursor : cursor + pair_size - 4]
        cursor += pair_size - 4
        if pair_id == APK_SIGNATURE_SCHEME_V2_ID:
            return block_start, block_end, value
    raise ValueError("APK Signature Scheme v2 pair missing")


def verify_output(output: Path) -> None:
    apk = output.read_bytes()
    block_start, block_end, v2_value = parse_v2_pair(apk)
    signers, _ = read_lp32(v2_value, 0)
    signer, _ = read_lp32(signers, 0)
    signed_data, cursor = read_lp32(signer, 0)
    signatures, cursor = read_lp32(signer, cursor)
    public_key_der, cursor = read_lp32(signer, cursor)

    digest_sequence, cursor = read_lp32(signed_data, 0)
    certificate_sequence, cursor = read_lp32(signed_data, cursor)
    _, cursor = read_lp32(signed_data, cursor)
    digest_record, _ = read_lp32(digest_sequence, 0)
    digest_algorithm = struct.unpack_from("<I", digest_record, 0)[0]
    expected_digest, _ = read_lp32(digest_record, 4)
    certificate_der, _ = read_lp32(certificate_sequence, 0)

    signature_record, _ = read_lp32(signatures, 0)
    signature_algorithm = struct.unpack_from("<I", signature_record, 0)[0]
    signature, _ = read_lp32(signature_record, 4)
    if digest_algorithm != RSA_PKCS1_SHA256_ID:
        raise ValueError("Unexpected digest algorithm")
    if signature_algorithm != RSA_PKCS1_SHA256_ID:
        raise ValueError("Unexpected signature algorithm")

    certificate = x509.load_der_x509_certificate(certificate_der)
    public_key = serialization.load_der_public_key(public_key_der)
    public_key.verify(signature, signed_data, padding.PKCS1v15(), hashes.SHA256())
    if public_key_der != certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ):
        raise ValueError("Signer public key does not match certificate")

    eocd_offset = find_eocd(apk)
    central_directory_offset = struct.unpack_from("<I", apk, eocd_offset + 16)[0]
    if central_directory_offset != block_end:
        raise ValueError("Central directory does not follow signing block")
    patched_eocd = bytearray(apk[eocd_offset:])
    struct.pack_into("<I", patched_eocd, 16, block_start)
    actual_digest = chunked_content_digest(
        [
            apk[:block_start],
            apk[block_end:eocd_offset],
            bytes(patched_eocd),
        ]
    )
    if actual_digest != expected_digest:
        raise ValueError("APK content digest mismatch")

    with ZipFile(output) as archive:
        bad_entry = archive.testzip()
        if bad_entry:
            raise ValueError(f"ZIP CRC failure: {bad_entry}")
        arm64 = [
            entry
            for entry in archive.infolist()
            if entry.filename.startswith("lib/arm64-v8a/")
            and entry.filename.endswith(".so")
        ]
        if not arm64:
            raise ValueError("No arm64 native libraries")
        stored = [entry.filename for entry in arm64 if entry.compress_type == ZIP_STORED]
        if stored:
            raise ValueError(f"Uncompressed arm64 libraries remain: {stored}")

        resources = archive.getinfo("resources.arsc")
        if resources.compress_type != ZIP_STORED:
            raise ValueError("resources.arsc must be stored uncompressed")
        local_header = resources.header_offset
        filename_size, extra_size = struct.unpack_from(
            "<HH", apk, local_header + 26
        )
        resource_data_offset = local_header + 30 + filename_size + extra_size
        if resource_data_offset % 4:
            raise ValueError(
                f"resources.arsc is not 4-byte aligned: {resource_data_offset}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ggq-repack-") as temp_dir:
        unsigned_path = Path(temp_dir) / "unsigned.apk"
        repack_unsigned(args.source, unsigned_path)
        fingerprint = sign_apk(unsigned_path, args.output)
    verify_output(args.output)
    print(f"APK: {args.output}")
    print(f"Size: {args.output.stat().st_size} bytes")
    print(f"SHA-256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(f"Signer certificate SHA-256: {fingerprint}")


if __name__ == "__main__":
    main()
