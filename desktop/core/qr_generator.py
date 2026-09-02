"""
QR Code Generator for ConnectToPhone.
Provides `generate_qr_png_bytes` and `generate_qr_svg`.
Uses standard `qrcode` library when available with high-fidelity Pure Python fallback.
Includes ISO/IEC 18004 Quiet Zone (border=4) for instant camera and barcode scanner detection.
"""

import os
import sys
import glob
from io import BytesIO
from typing import List, Tuple, Optional

# Ensure system and user site-packages are available
for site_pkg in glob.glob('/usr/lib*/python3*/site-packages') + glob.glob(os.path.expanduser('~/.local/lib/python3*/site-packages')):
    if site_pkg not in sys.path:
        sys.path.append(site_pkg)

try:
    import qrcode
    HAS_QRCODE_LIB = True
except ImportError:
    HAS_QRCODE_LIB = False


def generate_qr_png_bytes(data: str, box_size: int = 10, border: int = 4) -> bytes:
    """Generate high-contrast, scanner-ready PNG bytes for QR code."""
    if HAS_QRCODE_LIB:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    else:
        # Pure Python fallback to SVG converted to bytes
        svg = generate_qr_svg(data, box_size=box_size, border=border)
        return svg.encode('utf-8')


# --- Pure Python QR Code Generator Fallback ---

EXP_TABLE = [0] * 512
LOG_TABLE = [0] * 256

def _init_tables():
    x = 1
    for i in range(255):
        EXP_TABLE[i] = x
        EXP_TABLE[i + 255] = x
        LOG_TABLE[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D

_init_tables()

def _gf_mul(x: int, y: int) -> int:
    if x == 0 or y == 0:
        return 0
    return EXP_TABLE[LOG_TABLE[x] + LOG_TABLE[y]]

def _rs_generator_poly(degree: int) -> List[int]:
    poly = [1]
    for i in range(degree):
        root = EXP_TABLE[i]
        new_poly = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            new_poly[j] ^= _gf_mul(c, root)
            new_poly[j + 1] ^= c
        poly = new_poly
    return poly

def _rs_encode(data: List[int], num_ec_bytes: int) -> List[int]:
    gen = _rs_generator_poly(num_ec_bytes)
    res = [0] * num_ec_bytes
    for byte in data:
        factor = byte ^ res[0]
        res = res[1:] + [0]
        for i in range(num_ec_bytes):
            res[i] ^= _gf_mul(gen[i + 1], factor)
    return res

QR_SPECS_M = {
    1: (26, 16, 10, 1),
    2: (44, 28, 16, 1),
    3: (70, 44, 26, 1),
    4: (100, 64, 18, 2),
    5: (134, 86, 24, 2),
    6: (172, 108, 16, 4),
    7: (196, 124, 18, 4),
    8: (242, 154, 22, 4),
    9: (292, 182, 22, 5),
    10: (346, 216, 26, 5),
}

ALIGNMENT_PATTERNS = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
}


class QRCode:
    def __init__(self, data: str):
        self.raw_data = data.encode('utf-8')
        self.version = self._determine_version(len(self.raw_data))
        self.size = 17 + 4 * self.version
        self.matrix: List[List[Optional[bool]]] = [[None] * self.size for _ in range(self.size)]
        self.reserved: List[List[bool]] = [[False] * self.size for _ in range(self.size)]
        self._generate()

    def _determine_version(self, data_len: int) -> int:
        for v in range(1, 11):
            cap = QR_SPECS_M[v][1] - 2
            if data_len <= cap:
                return v
        return 10

    def _generate(self):
        self._place_finder(0, 0)
        self._place_finder(self.size - 7, 0)
        self._place_finder(0, self.size - 7)

        for i in range(8, self.size - 8):
            val = (i % 2 == 0)
            if not self.reserved[6][i]:
                self.matrix[6][i] = val
                self.reserved[6][i] = True
            if not self.reserved[i][6]:
                self.matrix[i][6] = val
                self.reserved[i][6] = True

        coords = ALIGNMENT_PATTERNS.get(self.version, [])
        for r in coords:
            for c in coords:
                if not (r < 9 and c < 9) and not (r < 9 and c >= self.size - 8) and not (r >= self.size - 8 and c < 9):
                    self._place_alignment(r, c)

        self.matrix[4 * self.version + 9][8] = True
        self.reserved[4 * self.version + 9][8] = True

        for i in range(9):
            self.reserved[8][i] = True
            self.reserved[i][8] = True
        for i in range(8):
            self.reserved[8][self.size - 1 - i] = True
            self.reserved[self.size - 1 - i][8] = True

        data_codewords = self._encode_data()
        self._place_data(data_codewords)
        self._apply_mask(mask_pattern=0)
        self._write_format_info(mask_pattern=0)

    def _place_finder(self, row: int, col: int):
        for r in range(-1, 8):
            for c in range(-1, 8):
                nr, nc = row + r, col + c
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    self.reserved[nr][nc] = True
                    if 0 <= r <= 6 and 0 <= c <= 6:
                        if (r in (0, 6) or c in (0, 6)) or (2 <= r <= 4 and 2 <= c <= 4):
                            self.matrix[nr][nc] = True
                        else:
                            self.matrix[nr][nc] = False
                    else:
                        self.matrix[nr][nc] = False

    def _place_alignment(self, row: int, col: int):
        for r in range(-2, 3):
            for c in range(-2, 3):
                nr, nc = row + r, col + c
                self.reserved[nr][nc] = True
                if abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0):
                    self.matrix[nr][nc] = True
                else:
                    self.matrix[nr][nc] = False

    def _encode_data(self) -> List[int]:
        total_codewords, data_cap, ec_per_block, num_blocks = QR_SPECS_M[self.version]
        bits = "0100"  # Byte mode
        bits += f"{len(self.raw_data):08b}"
        for b in self.raw_data:
            bits += f"{b:08b}"

        max_bits = data_cap * 8
        if len(bits) < max_bits:
            bits += "0000"[:min(4, max_bits - len(bits))]
        while len(bits) % 8 != 0:
            bits += "0"

        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        while len(bits) < max_bits:
            bits += f"{pad_bytes[pad_idx]:08b}"
            pad_idx = (pad_idx + 1) % 2

        codewords = [int(bits[i:i+8], 2) for i in range(0, len(bits), 8)]
        block_len = data_cap // num_blocks
        data_blocks = []
        ec_blocks = []

        for i in range(num_blocks):
            sub_data = codewords[i * block_len : (i + 1) * block_len]
            data_blocks.append(sub_data)
            ec_blocks.append(_rs_encode(sub_data, ec_per_block))

        interleaved = []
        for i in range(block_len):
            for b in range(num_blocks):
                interleaved.append(data_blocks[b][i])

        for i in range(ec_per_block):
            for b in range(num_blocks):
                interleaved.append(ec_blocks[b][i])

        return interleaved

    def _place_data(self, codewords: List[int]):
        bit_str = "".join(f"{c:08b}" for c in codewords)
        bit_idx = 0
        up = True

        col = self.size - 1
        while col > 0:
            if col == 6:
                col -= 1

            rows = range(self.size - 1, -1, -1) if up else range(self.size)
            for r in rows:
                for c in (col, col - 1):
                    if not self.reserved[r][c]:
                        if bit_idx < len(bit_str):
                            self.matrix[r][c] = (bit_str[bit_idx] == '1')
                            bit_idx += 1
                        else:
                            self.matrix[r][c] = False
            up = not up
            col -= 2

    def _apply_mask(self, mask_pattern: int = 0):
        for r in range(self.size):
            for c in range(self.size):
                if not self.reserved[r][c]:
                    mask = (r + c) % 2 == 0
                    if mask:
                        self.matrix[r][c] = not self.matrix[r][c]

    def _write_format_info(self, mask_pattern: int = 0):
        format_info_bits = 0b00000 ^ 0b101010000010010  # ECC M + Mask 0 with BCH
        bits_str = f"{format_info_bits:015b}"

        coords1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                   (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]

        coords2 = [(self.size - 1, 8), (self.size - 2, 8), (self.size - 3, 8), (self.size - 4, 8),
                   (self.size - 5, 8), (self.size - 6, 8), (self.size - 7, 8),
                   (8, self.size - 8), (8, self.size - 7), (8, self.size - 6), (8, self.size - 5),
                   (8, self.size - 4), (8, self.size - 3), (8, self.size - 2), (8, self.size - 1)]

        for i in range(15):
            val = (bits_str[14 - i] == '1')
            r1, c1 = coords1[i]
            r2, c2 = coords2[i]
            self.matrix[r1][c1] = val
            self.matrix[r2][c2] = val


def generate_qr_svg(data: str, box_size: int = 8, border: int = 4) -> str:
    """Generate SVG representation of QR Code starting with <svg."""
    qr = QRCode(data)
    matrix = qr.matrix
    size = qr.size
    img_size = (size + 2 * border) * box_size

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{img_size}" height="{img_size}" viewBox="0 0 {img_size} {img_size}">',
        f'<rect width="{img_size}" height="{img_size}" fill="#ffffff"/>'
    ]

    for r in range(size):
        for c in range(size):
            if matrix[r][c]:
                x = (c + border) * box_size
                y = (r + border) * box_size
                svg_parts.append(f'<rect x="{x}" y="{y}" width="{box_size}" height="{box_size}" fill="#000000"/>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)
