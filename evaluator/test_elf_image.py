import struct
import tempfile
import unittest
from pathlib import Path

from evaluator.elf_image import MEMORY_BASE, MEMORY_SIZE, TOHOST, load_elf


def make_elf(path: Path, segments: list[tuple[int, bytes, int]],
             entry: int = MEMORY_BASE) -> None:
    phoff = 52
    offset = phoff + 32 * len(segments)
    headers = []
    data = bytearray()
    for address, payload, memsz in segments:
        headers.append(struct.pack("<IIIIIIII", 1, offset, address, address,
                                   len(payload), memsz, 5, 4))
        data.extend(payload)
        offset += len(payload)
    elf_header = struct.pack("<16sHHIIIIIHHHHHH",
                             b"\x7fELF\x01\x01\x01" + bytes(9),
                             2, 243, 1, entry, phoff, 0, 0,
                             52, 32, len(segments), 0, 0, 0)
    path.write_bytes(elf_header + b"".join(headers) + data)


class ElfImageTest(unittest.TestCase):
    def test_load_and_zero_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.elf"
            make_elf(path, [(MEMORY_BASE, b"\x93\x00\x10\x00", 8)])
            image = load_elf(path)
            self.assertEqual(len(image), MEMORY_SIZE)
            self.assertEqual(image[:8], b"\x93\x00\x10\x00" + bytes(4))

    def test_reject_overlapping_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.elf"
            make_elf(path, [(MEMORY_BASE, bytes(8), 8),
                            (MEMORY_BASE + 4, bytes(4), 4)])
            with self.assertRaisesRegex(ValueError, "overlaps another segment"):
                load_elf(path)

    def test_reject_tohost_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.elf"
            make_elf(path, [(MEMORY_BASE, bytes(4), 4), (TOHOST, bytes(4), 4)])
            with self.assertRaisesRegex(ValueError, "tohost"):
                load_elf(path)

    def test_reject_wrong_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.elf"
            make_elf(path, [(MEMORY_BASE, bytes(4), 4)], MEMORY_BASE + 4)
            with self.assertRaisesRegex(ValueError, "entry"):
                load_elf(path)


if __name__ == "__main__":
    unittest.main()
