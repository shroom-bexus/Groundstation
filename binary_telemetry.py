"""SHB1 decoder. Returns existing telemetry lines without numeric rounding."""
import struct

DICTIONARY = (b"AIRDOS", b"$E", b"$START", b"$STOP", b"$ENV", b"HEALTH",
              b"PADS", b"THERMAL", b"MAX31865", b"RTC", b"OK", b"FAULT",
              b"PLATE_LIMIT")
MAX_PACKET = 1200
MAX_LINE = 1151


def decode_datagram(data):
    if not data.startswith(b"SHB"):
        return data.decode("utf-8", errors="replace").splitlines()
    if data[:4] != b"SHB1" or not 11 <= len(data) <= MAX_PACKET:
        raise ValueError("unsupported or truncated binary telemetry header")
    lines = [f"SEQ,{struct.unpack_from('<I', data, 4)[0]}"]
    pos = 8
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError("truncated record length")
        size = int.from_bytes(data[pos:pos+2], "little")
        pos += 2
        end = pos + size
        if size < 1 or end > len(data):
            raise ValueError("invalid record length")
        mode = data[pos]
        pos += 1
        if mode == 0:
            raw = data[pos:end]
            pos = end
        elif mode == 1:
            fields = []
            length = 0
            while pos < end:
                tag = data[pos]
                pos += 1
                if tag < 240:
                    field = str(tag).encode("ascii")
                elif tag == 240:
                    if pos + 4 > end:
                        raise ValueError("truncated integer")
                    field = str(int.from_bytes(data[pos:pos+4], "little")).encode("ascii")
                    pos += 4
                elif tag == 241:
                    if pos + 2 > end:
                        raise ValueError("truncated text length")
                    n = int.from_bytes(data[pos:pos+2], "little")
                    pos += 2
                    if pos + n > end:
                        raise ValueError("truncated text")
                    field = data[pos:pos+n]
                    pos += n
                elif tag == 242:
                    if pos >= end or data[pos] >= len(DICTIONARY):
                        raise ValueError("invalid dictionary index")
                    field = DICTIONARY[data[pos]]
                    pos += 1
                else:
                    raise ValueError("unknown field tag")
                length += len(field) + bool(fields)
                if length > MAX_LINE:
                    raise ValueError("decoded line too long")
                fields.append(field)
            if not fields:
                raise ValueError("empty token record")
            raw = b",".join(fields)
        else:
            raise ValueError("unknown record mode")
        if len(raw) > MAX_LINE or any(c in raw for c in (b"\n", b"\r", b"\0")):
            raise ValueError("invalid decoded line")
        lines.append(raw.decode("utf-8", errors="strict"))
    return lines
