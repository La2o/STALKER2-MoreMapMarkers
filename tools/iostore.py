"""Minimal reader/writer for Unreal Engine 5.1 IoStore containers, as used by
S.T.A.L.K.E.R. 2 (.utoc TOC version 5, container header version 2).

Reading handles everything the game's own containers use (Oodle blocks,
multiple partitions, directory index, container header). Writing produces a
small uncompressed container plus the empty companion .pak needed to mount it.
"""
import hashlib
import os
import struct
import zlib

import blake3

TOC_MAGIC = b"-==--==--==--==-"
TOC_VERSION = 5  # PerfectHashWithOverflow
TOC_HEADER_SIZE = 0x90
CONTAINER_HEADER_MAGIC = 0x496F436E
CONTAINER_HEADER_VERSION = 2  # OptionalSegmentPackages

FLAG_COMPRESSED = 0x1
FLAG_ENCRYPTED = 0x2
FLAG_SIGNED = 0x4
FLAG_INDEXED = 0x8

CHUNK_EXPORT_BUNDLE_DATA = 1
CHUNK_CONTAINER_HEADER = 6

BLOCK_SIZE = 0x40000
BLOCK_ALIGN = 16
NO_PARTITION_SIZE = 0xFFFFFFFFFFFFFFFF
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x00000100000001B3
MASK64 = 0xFFFFFFFFFFFFFFFF


# --- ids and hashes -------------------------------------------------------

def chunk_id(object_id, chunk_type, index=0):
    """FIoChunkId: u64 id (LE), u16 index (BE), u8 padding, u8 type."""
    return struct.pack("<Q", object_id) + struct.pack(">H", index) + bytes((0, chunk_type))


def chunk_hash(data):
    """FIoChunkHash: BLAKE3 truncated to 20 bytes, zero-padded to 32."""
    return blake3.blake3(data).digest()[:20] + b"\0" * 12


def hash_chunk_id(seed, cid):
    """FIoStoreTocResource::HashChunkIdWithSeed (FNV-1a variant)."""
    h = seed if seed else FNV_OFFSET
    for b in cid:
        h = ((h * FNV_PRIME) & MASK64) ^ b
    return h


# --- serialization helpers ------------------------------------------------

class Reader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def take(self, n):
        b = self.data[self.pos : self.pos + n]
        if len(b) != n:
            raise ValueError("unexpected end of data")
        self.pos += n
        return b

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.take(8))[0]

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ""
        if n < 0:
            return self.take(-n * 2).decode("utf-16-le")[:-1]
        return self.take(n).decode("latin-1")[:-1]


def fstring(s):
    if not s:
        return struct.pack("<i", 0)
    try:
        raw = s.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    except UnicodeEncodeError:
        raw = s.encode("utf-16-le") + b"\0\0"
        return struct.pack("<i", -(len(raw) // 2)) + raw


# --- reading --------------------------------------------------------------

class Container:
    """A .utoc/.ucas container opened for reading."""

    def __init__(self, utoc_path):
        self.path = utoc_path
        toc = open(utoc_path, "rb").read()
        r = Reader(toc)
        if r.take(16) != TOC_MAGIC:
            raise ValueError(f"{utoc_path}: not a .utoc file")
        self.version = r.u8()
        r.take(3)
        header_size = r.u32()
        n_entries = r.u32()
        n_blocks = r.u32()
        block_entry_size = r.u32()
        n_methods = r.u32()
        method_len = r.u32()
        self.block_size = r.u32()
        dir_size = r.u32()
        self.partition_count = r.u32()
        self.container_id = r.u64()
        r.take(16)  # encryption key guid
        self.flags = r.u8()
        r.take(3)
        n_seeds = r.u32()
        self.partition_size = r.u64()
        n_overflow = r.u32()
        if self.version < 5 or block_entry_size != 12:
            raise ValueError(f"{utoc_path}: unsupported TOC version {self.version}")
        if self.flags & FLAG_ENCRYPTED:
            raise ValueError(f"{utoc_path}: container is encrypted")

        r.pos = header_size
        self.chunk_ids = [r.take(12) for _ in range(n_entries)]
        self.offsets = []
        for _ in range(n_entries):
            e = r.take(10)
            self.offsets.append((int.from_bytes(e[:5], "big"), int.from_bytes(e[5:], "big")))
        r.take(4 * n_seeds + 4 * n_overflow)
        self.blocks = []
        for _ in range(n_blocks):
            e = r.take(12)
            self.blocks.append((int.from_bytes(e[:5], "little"), int.from_bytes(e[5:8], "little"),
                                int.from_bytes(e[8:11], "little"), e[11]))
        self.methods = [r.take(method_len).rstrip(b"\0").decode() for _ in range(n_methods)]
        if self.flags & FLAG_SIGNED:
            hash_size = r.i32()
            r.take(hash_size * 2 + 20 * n_blocks)
        self.directory = r.take(dir_size) if self.flags & FLAG_INDEXED else b""
        self.metas = [r.take(33) for _ in range(n_entries)]
        self.index = {cid: i for i, cid in enumerate(self.chunk_ids)}
        self._partitions = {}

    def _partition(self, n):
        if n not in self._partitions:
            base = self.path[: -len(".utoc")]
            path = base + (".ucas" if n == 0 else f"_s{n}.ucas")
            self._partitions[n] = open(path, "rb")
        return self._partitions[n]

    def _read_physical(self, offset, size):
        if self.partition_size in (0, NO_PARTITION_SIZE):
            part, off = 0, offset
        else:
            part, off = divmod(offset, self.partition_size)
        f = self._partition(part)
        f.seek(off)
        return f.read(size)

    def read_chunk(self, index, verify=True):
        offset, length = self.offsets[index]
        if length == 0:
            return b""
        first = offset // self.block_size
        last = (offset + length - 1) // self.block_size
        out = bytearray()
        for b in range(first, last + 1):
            phys, csize, usize, method = self.blocks[b]
            raw = self._read_physical(phys, align(csize))[:csize]
            if method == 0:
                out += raw[:usize]
            else:
                name = self.methods[method - 1]
                if name.lower() != "oodle":
                    raise ValueError(f"unsupported compression method {name}")
                import ooz
                out += ooz.decompress(raw, usize)
        start = offset - first * self.block_size
        data = bytes(out[start : start + length])
        if verify and chunk_hash(data)[:20] != self.metas[index][:20]:
            raise ValueError(f"{self.path}: hash mismatch on chunk {index}")
        return data

    def files(self):
        """Yield (path, toc entry index) for every file in the directory index."""
        if not self.directory:
            return
        r = Reader(self.directory)
        mount = r.fstring()
        dirs = [(r.u32(), r.u32(), r.u32(), r.u32()) for _ in range(r.u32())]
        files = [(r.u32(), r.u32(), r.u32()) for _ in range(r.u32())]
        strings = [r.fstring() for _ in range(r.u32())]
        NONE = 0xFFFFFFFF

        def walk(d, prefix):
            name, child, _, file = dirs[d]
            if name != NONE:
                prefix += strings[name] + "/"
            while file != NONE:
                fname, file, entry = files[file]
                yield prefix + strings[fname], entry
            while child != NONE:
                yield from walk(child, prefix)
                child = dirs[child][2]

        if dirs:
            yield from walk(0, mount)

    def container_header(self):
        cid = chunk_id(self.container_id, CHUNK_CONTAINER_HEADER)
        if cid not in self.index:
            return None
        return parse_container_header(self.read_chunk(self.index[cid]))


def parse_container_header(data):
    r = Reader(data)
    if r.u32() != CONTAINER_HEADER_MAGIC:
        raise ValueError("bad container header magic")
    version = r.u32()
    if version != CONTAINER_HEADER_VERSION:
        raise ValueError(f"unsupported container header version {version}")
    container_id = r.u64()
    package_ids = [r.u64() for _ in range(r.u32())]
    store = r.take(r.u32())
    entries = {}
    for i, pid in enumerate(package_ids):
        base = i * 24
        er = Reader(store, base)
        export_count, bundle_count = er.i32(), er.i32()
        arrays = []
        for field_off, item_size in ((8, 8), (16, 20)):
            n, rel = er.u32(), er.u32()
            start = base + field_off + rel
            arrays.append(store[start : start + n * item_size] if n else b"")
        imports = [struct.unpack_from("<Q", arrays[0], j * 8)[0] for j in range(len(arrays[0]) // 8)]
        shader_maps = [arrays[1][j * 20 : j * 20 + 20] for j in range(len(arrays[1]) // 20)]
        entries[pid] = (export_count, bundle_count, imports, shader_maps)
    return {"container_id": container_id, "entries": entries}


# --- writing --------------------------------------------------------------

def align(n, a=BLOCK_ALIGN):
    return (n + a - 1) // a * a


def write_container_header(container_id, entries):
    """entries: {package_id: (export_count, bundle_count, imports, shader_maps)}"""
    pids = list(entries)
    fixed = bytearray()
    tail = bytearray()
    base_tail = 24 * len(pids)
    for i, pid in enumerate(pids):
        export_count, bundle_count, imports, shader_maps = entries[pid]
        entry = struct.pack("<ii", export_count, bundle_count)
        for field_off, items in ((8, [struct.pack("<Q", x) for x in imports]), (16, shader_maps)):
            if items:
                rel = base_tail + len(tail) - (i * 24 + field_off)
                entry += struct.pack("<II", len(items), rel)
                tail += b"".join(items)
            else:
                entry += struct.pack("<II", 0, 0)
        fixed += entry
    store = bytes(fixed + tail)
    out = struct.pack("<IIQ", CONTAINER_HEADER_MAGIC, CONTAINER_HEADER_VERSION, container_id)
    out += struct.pack("<I", len(pids)) + b"".join(struct.pack("<Q", p) for p in pids)
    out += struct.pack("<I", len(store)) + store
    out += struct.pack("<II", 0, 0)  # optional segment package ids, store entries
    # Empty redirects name map: count, string bytes, hash version
    out += struct.pack("<IIQ", 0, 0, 0xC1640000)
    out += struct.pack("<II", 0, 0)  # localized packages, package redirects
    return out


def write_directory_index(mount_point, files):
    """files: list of (relative path, toc entry index)."""
    strings, string_ix = [], {}

    def sid(s):
        if s not in string_ix:
            string_ix[s] = len(strings)
            strings.append(s)
        return string_ix[s]

    NONE = 0xFFFFFFFF
    dirs = [[NONE, NONE, NONE, NONE]]  # name, first child, next sibling, first file
    file_entries = []
    children = [{}]
    for path, entry in files:
        *parts, fname = path.split("/")
        d = 0
        for part in parts:
            if part not in children[d]:
                dirs.append([sid(part), NONE, NONE, NONE])
                children.append({})
                new = len(dirs) - 1
                dirs[new][2] = dirs[d][1]
                dirs[d][1] = new
                children[d][part] = new
            d = children[d][part]
        file_entries.append([sid(fname), dirs[d][3], entry])
        dirs[d][3] = len(file_entries) - 1

    out = fstring(mount_point)
    out += struct.pack("<I", len(dirs)) + b"".join(struct.pack("<4I", *d) for d in dirs)
    out += struct.pack("<I", len(file_entries)) + b"".join(struct.pack("<3I", *f) for f in file_entries)
    out += struct.pack("<I", len(strings)) + b"".join(fstring(s) for s in strings)
    return out


def perfect_hash(chunk_ids):
    """Order chunk ids into perfect-hash slots. Returns (ordered ids, seeds)."""
    n = len(chunk_ids)
    buckets = [[] for _ in range(n)]
    for cid in chunk_ids:
        buckets[hash_chunk_id(0, cid) % n].append(cid)
    seeds = [0] * n
    slots = [None] * n
    for b in sorted(range(n), key=lambda b: -len(buckets[b])):
        items = buckets[b]
        if not items:
            continue
        seed = 1
        while True:
            want = [hash_chunk_id(seed, c) % n for c in items]
            if len(set(want)) == len(want) and all(slots[s] is None for s in want):
                break
            seed += 1
            if seed > 1_000_000:
                raise RuntimeError("no perfect hash seed found")
        for s, c in zip(want, items):
            slots[s] = c
        seeds[b] = seed
    return slots, seeds


def write_container(base_path, name, mount_point, files, chunks):
    """Write <base_path>.utoc/.ucas/.pak.

    files:  [(path relative to mount point, chunk id)]
    chunks: {chunk id: (data, store entry)}; the store entry
            (export_count, bundle_count, imports, shader_maps) is needed for
            export bundle chunks and None otherwise. The container header
            chunk is added here.
    """
    container_id = struct.unpack("<Q", blake3.blake3(name.lower().encode("utf-16-le")).digest()[:8])[0]
    if container_id == MASK64:
        container_id -= 1
    chunks = dict(chunks)
    chunks[chunk_id(container_id, CHUNK_CONTAINER_HEADER)] = (b"", None)  # filled below

    ids, seeds = perfect_hash(list(chunks))
    slot = {cid: i for i, cid in enumerate(ids)}

    # The container header lists every package (export bundle chunk) we ship.
    header_entries = {}
    for cid, data in chunks.items():
        if cid[11] == CHUNK_EXPORT_BUNDLE_DATA:
            header_entries[struct.unpack("<Q", cid[:8])[0]] = data[1]
    chunks[chunk_id(container_id, CHUNK_CONTAINER_HEADER)] = (
        write_container_header(container_id, header_entries), None)

    ucas = bytearray()
    blocks, offsets = [], []
    virtual = 0
    for cid in ids:
        data = chunks[cid][0]
        offsets.append((virtual, len(data)))
        for i in range(0, max(len(data), 1), BLOCK_SIZE):
            part = data[i : i + BLOCK_SIZE]
            blocks.append((len(ucas), len(part)))
            ucas += part
            ucas += b"\0" * (align(len(ucas)) - len(ucas))
        virtual += max(align(len(data), BLOCK_SIZE), BLOCK_SIZE)

    directory = write_directory_index(mount_point, [(p, slot[c]) for p, c in files])
    methods = [b"Oodle".ljust(32, b"\0")]  # listed like the game does; no block uses it

    toc = bytearray()
    toc += TOC_MAGIC
    toc += struct.pack("<BBH", TOC_VERSION, 0, 0)
    toc += struct.pack("<8I", TOC_HEADER_SIZE, len(ids), len(blocks), 12, len(methods), 32,
                       BLOCK_SIZE, len(directory))
    toc += struct.pack("<IQ", 1, container_id)
    toc += b"\0" * 16  # encryption key guid
    toc += struct.pack("<B3x", FLAG_INDEXED)
    toc += struct.pack("<IQII", len(seeds), NO_PARTITION_SIZE, 0, 0)
    toc += b"\0" * (TOC_HEADER_SIZE - len(toc))
    toc += b"".join(ids)
    toc += b"".join(o.to_bytes(5, "big") + n.to_bytes(5, "big") for o, n in offsets)
    toc += b"".join(struct.pack("<i", s) for s in seeds)
    toc += b"".join(o.to_bytes(5, "little") + n.to_bytes(3, "little") * 2 + b"\0" for o, n in blocks)
    toc += b"".join(methods)
    toc += directory
    toc += b"".join(chunk_hash(chunks[c][0]) + b"\0" for c in ids)

    with open(base_path + ".utoc", "wb") as f:
        f.write(toc)
    with open(base_path + ".ucas", "wb") as f:
        f.write(ucas)
    with open(base_path + ".pak", "wb") as f:
        f.write(empty_pak(name))


def empty_pak(name):
    """A version 11 .pak with no files; UE needs one to mount the IoStore container."""
    path_hash_index = struct.pack("<I", 0) + struct.pack("<I", 0)
    full_dir_index = struct.pack("<I", 0)
    index_size = 0
    seed = zlib.crc32(name.lower().encode("utf-16-le"))

    def build_index(index_size):
        idx = fstring("/")
        idx += struct.pack("<iQ", 0, seed)
        idx += struct.pack("<iqq", 1, index_size, len(path_hash_index))
        idx += hashlib.sha1(path_hash_index).digest()
        idx += struct.pack("<iqq", 1, index_size + len(path_hash_index), len(full_dir_index))
        idx += hashlib.sha1(full_dir_index).digest()
        idx += struct.pack("<II", 0, 0)  # encoded entries size, non-encoded entry count
        return idx

    index = build_index(0)
    index = build_index(len(index))
    footer = b"\0" * 16 + b"\0" + struct.pack("<IIqq", 0x5A6F12E1, 11, 0, len(index))
    footer += hashlib.sha1(index).digest() + b"\0" * (5 * 32)
    return index + path_hash_index + full_dir_index + footer
