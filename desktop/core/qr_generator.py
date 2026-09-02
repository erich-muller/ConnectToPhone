"""
Pure Python QR Code Generator for ConnectToPhone.
Self-contained implementation of QR Code Model 2 (Byte Mode) with Reed-Solomon error correction.
Zero external library dependencies (optionally renders to Cairo, Pillow, or SVG).
"""

import math
from typing import List, Tuple, Optional

# --- Reed-Solomon Galois Field GF(256) Arithmetic ---

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
            x ^= 0x11D  # Primitive polynomial: x^8 + x^4 + x^3 + x^2 + 1

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

# QR Code Specifications (Version, Capacity in Bytes for ECC Level M, EC bytes per block, blocks)
# Version: (total_codewords, data_codewords_M, ec_codewords_per_block, num_blocks)
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
            cap = QR_SPECS_M[v][1] - 2  # 2 bytes overhead (mode indicator + length)
            if data_len <= cap:
                return v
        return 10  # fallback to version 10

    def _generate(self):
        # 1. Place Function Patterns
        self._place_finder_patterns()
        self._place_alignment_patterns()
        self._place_timing_patterns()
        self._reserve_format_areas()

        # 2. Encode Data and Error Correction
        codewords = self._encode_data()
        
        # 3. Place Data Bits
        self._place_data_bits(codewords)

        # 4. Apply Mask Pattern (Mask pattern 0: (row + col) % 2 == 0)
        self._apply_mask(0)

        # 5. Place Format Information (ECC M, Mask 0 -> 0x5412 XOR)
        self._place_format_info(0)

    def _set_module(self, r: int, c: int, val: bool, is_reserved: bool = True):
        self.matrix[r][c] = val
        if is_reserved:
            self.reserved[r][c] = True

    def _place_finder_patterns(self):
        def draw_finder(top_r: int, left_c: int):
            for r in range(7):
                for c in range(7):
                    if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                        self._set_module(top_r + r, left_c + c, True)
                    else:
                        self._set_module(top_r + r, left_c + c, False)
            # Separators
            for r in range(max(0, top_r - 1), min(self.size, top_r + 8)):
                for c in range(max(0, left_c - 1), min(self.size, left_c + 8)):
                    if self.matrix[r][c] is None:
                        self._set_module(r, c, False)

        draw_finder(0, 0)
        draw_finder(0, self.size - 7)
        draw_finder(self.size - 7, 0)

    def _place_alignment_patterns(self):
        coords = ALIGNMENT_PATTERNS.get(self.version, [])
        for r in coords:
            for c in coords:
                # Skip if overlapping with finder patterns
                if (r < 9 and c < 9) or (r < 9 and c > self.size - 9) or (r > self.size - 9 and c < 9):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        val = (abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0))
                        self._set_module(r + dr, c + dc, val)

    def _place_timing_patterns(self):
        for i in range(8, self.size - 8):
            if self.matrix[6][i] is None:
                self._set_module(6, i, i % 2 == 0)
            if self.matrix[i][6] is None:
                self._set_module(i, 6, i % 2 == 0)

    def _reserve_format_areas(self):
        for i in range(9):
            if self.matrix[8][i] is None:
                self.reserved[8][i] = True
            if self.matrix[i][8] is None:
                self.reserved[i][8] = True
        for i in range(self.size - 8, self.size):
            self.reserved[8][i] = True
            self.reserved[i][8] = True
        # Dark module
        self._set_module(4 * self.version + 9, 8, True)

    def _encode_data(self) -> List[int]:
        # Mode: Byte mode (0100)
        bits = "0100"
        char_count_len = 8 if self.version < 10 else 16
        bits += f"{len(self.raw_data):0{char_count_len}b}"
        
        for byte in self.raw_data:
            bits += f"{byte:08b}"

        total_data_bytes = QR_SPECS_M[self.version][1]
        total_data_bits = total_data_bytes * 8

        # Terminator
        terminator_len = min(4, total_data_bits - len(bits))
        bits += "0" * terminator_len

        # Pad to byte boundary
        if len(bits) % 8 != 0:
            bits += "0" * (8 - (len(bits) % 8))

        # Pad bytes
        pad_bytes = ["11101100", "00010001"]
        pad_idx = 0
        while len(bits) < total_data_bits:
            bits += pad_bytes[pad_idx % 2]
            pad_idx += 1

        # Convert to byte array
        data_bytes = [int(bits[i:i+8], 2) for i in range(0, len(bits), 8)]

        # Error correction blocks
        total_cw, data_cw, ec_cw_per_block, num_blocks = QR_SPECS_M[self.version]
        bytes_per_block = data_cw // num_blocks
        
        blocks_data = []
        blocks_ec = []
        
        start = 0
        for b in range(num_blocks):
            end = start + bytes_per_block
            block = data_bytes[start:end]
            blocks_data.append(block)
            ec = _rs_encode(block, ec_cw_per_block)
            blocks_ec.append(ec)
            start = end

        # Interleave data and EC bytes
        final_codewords = []
        for i in range(bytes_per_block):
            for b in range(num_blocks):
                final_codewords.append(blocks_data[b][i])
        for i in range(ec_cw_per_block):
            for b in range(num_blocks):
                final_codewords.append(blocks_ec[b][i])

        return final_codewords

    def _place_data_bits(self, codewords: List[int]):
        bit_str = "".join(f"{b:08b}" for b in codewords)
        bit_idx = 0
        bit_len = len(bit_str)

        row = self.size - 1
        col = self.size - 1
        direction = -1  # Upward

        while col > 0:
            if col == 6:
                col -= 1  # Skip vertical timing pattern
            for r_offset in range(self.size):
                curr_row = row + (direction * r_offset) if direction == -1 else r_offset
                for c_offset in range(2):
                    curr_col = col - c_offset
                    if not self.reserved[curr_row][curr_col]:
                        val = (bit_str[bit_idx] == '1') if bit_idx < bit_len else False
                        self.matrix[curr_row][curr_col] = val
                        bit_idx += 1

            direction = -direction
            col -= 2

    def _apply_mask(self, mask_pattern: int = 0):
        for r in range(self.size):
            for c in range(self.size):
                if not self.reserved[r][c]:
                    # Mask 0: (row + col) % 2 == 0
                    if (r + c) % 2 == 0:
                        self.matrix[r][c] = not self.matrix[r][c]

    def _place_format_info(self, mask: int = 0):
        fmt_str = "101010000010010"
        
        # Around top-left finder
        for i in range(6):
            self.matrix[8][i] = (fmt_str[i] == '1')
        self.matrix[8][7] = (fmt_str[6] == '1')
        self.matrix[8][8] = (fmt_str[7] == '1')
        self.matrix[7][8] = (fmt_str[8] == '1')
        for i in range(6):
            self.matrix[5 - i][8] = (fmt_str[9 + i] == '1')

        # Split around other finders
        for i in range(7):
            self.matrix[self.size - 1 - i][8] = (fmt_str[i] == '1')
        for i in range(8):
            self.matrix[8][self.size - 8 + i] = (fmt_str[7 + i] == '1')

    def to_svg(self, box_size: int = 8, border: int = 2, fg_color: str = "#1E1E2E", bg_color: str = "#FFFFFF") -> str:
        """Render matrix to scalable SVG string."""
        dim = (self.size + border * 2) * box_size
        rects = []
        for r in range(self.size):
            for c in range(self.size):
                if self.matrix[r][c]:
                    x = (c + border) * box_size
                    y = (r + border) * box_size
                    rects.append(f'<rect x="{x}" y="{y}" width="{box_size}" height="{box_size}" fill="{fg_color}" />')
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" width="{dim}" height="{dim}">
  <rect width="100%" height="100%" fill="{bg_color}" rx="12" ry="12"/>
  {''.join(rects)}
</svg>'''
        return svg

    def render_cairo(self, context, width: int, height: int, fg_color: Tuple[float, float, float] = (0.1, 0.1, 0.1), bg_color: Tuple[float, float, float] = (1.0, 1.0, 1.0), border: int = 2):
        """Render to an active PyCairo context."""
        context.save()
        
        # Fill background with rounded rect
        context.set_source_rgb(*bg_color)
        context.rectangle(0, 0, width, height)
        context.fill()

        total_modules = self.size + border * 2
        module_size = min(width, height) / total_modules
        offset_x = (width - (total_modules * module_size)) / 2.0
        offset_y = (height - (total_modules * module_size)) / 2.0

        context.set_source_rgb(*fg_color)
        for r in range(self.size):
            for c in range(self.size):
                if self.matrix[r][c]:
                    x = offset_x + (c + border) * module_size
                    y = offset_y + (r + border) * module_size
                    context.rectangle(x, y, module_size, module_size)
        context.fill()
        context.restore()


def generate_qr_svg(data: str, box_size: int = 8, border: int = 2) -> str:
    """Convenience helper to generate an SVG string directly."""
    qr = QRCode(data)
    return qr.to_svg(box_size=box_size, border=border)

