import json
import tarfile
from typing import NamedTuple


_UINT32_SIZE = b'\x04\x00\x00\x00'


class FileRecord(NamedTuple):
    path: str
    offset: int
    size: int
    executable: bool


def _read_exact(f, count):
    result = f.read(count)

    if len(result) != count:
        raise ValueError('Unexpected end of Asar file')

    return result


def _expect(expectation):
    if not expectation:
        raise ValueError('Unexpected data in Asar file')


def _read_uint4_le(f):
    return int.from_bytes(_read_exact(f, 4), 'little')


def _read_padding(f, size):
    _expect(0 <= size < 4)

    if size != 0:
        _expect(f.read(size) == b'\0' * size)


def _flatten(path, index):
    for key, value in index.items():
        _expect(key and '/' not in key and key not in {'.', '..'})

        if 'files' in value:
            yield from _flatten(path + (key,), value['files'])
        else:
            raw_offset = value['offset']
            raw_size = value['size']
            raw_executable = value.get('executable', False)

            _expect(isinstance(raw_offset, str))
            _expect(isinstance(raw_size, int))
            _expect(isinstance(raw_executable, bool))

            offset = int(raw_offset)

            _expect(offset >= 0)
            _expect(raw_size >= 0)

            yield FileRecord(path + (key,), offset, raw_size, raw_executable)


def transform(f, out):
    # header_size header
    _expect(f.read(4) == _UINT32_SIZE)

    # header_size
    header_pickled_size = _read_uint4_le(f) - 4

    # header header
    _expect(_read_uint4_le(f) == header_pickled_size)

    # header header 2: return of the length prefixes
    header_unpadded_size = _read_uint4_le(f)
    padding_size = header_pickled_size - 4 - header_unpadded_size

    header_bytes = _read_exact(f, header_unpadded_size)
    header = json.loads(header_bytes)

    _read_padding(f, padding_size)

    offset = 0

    for r in sorted(_flatten((), header['files']), key=lambda r: r.offset):
        _expect(offset == r.offset)
        offset = r.offset + r.size

        info = tarfile.TarInfo(name='/'.join(r.path))
        info.size = r.size
        info.mode = 0o755 if r.executable else 0o644
        out.addfile(info, f)


if __name__ == '__main__':
    import sys

    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as out:
        transform(sys.stdin.buffer, out)
