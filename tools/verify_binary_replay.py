#!/usr/bin/env python3
"""Cross-language roundtrip and nine-sensor production-queue replay.
Usage: python tools/verify_binary_replay.py ../Flight_Software radiation.jsonl
Requires g++; writes only temporary executables and inputs.
"""
import collections
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from binary_telemetry import decode_datagram


def main():
    flight = Path(sys.argv[1]).resolve()
    rows = [json.loads(line) for line in Path(sys.argv[2]).read_text().splitlines()]
    rows.sort(key=lambda x: x["timestamp_unix_ms"])
    start = rows[0]["timestamp_unix_ms"]
    lines = [f"AIRDOS,{r['timestamp_unix_ms']-start},1,{r['message']}" for r in rows]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        for name in ("codec", "replay"):
            subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-DFLIGHT_PRIMARY=1", "-I"+str(flight/"test/binary"),
                            "-I"+str(flight/"include"),
                            str(flight/f"test/binary/{name}.cpp"), "-o", str(tmp/name)], check=True)
        # Numerical boundaries, empty fields and preservation of formatting.
        extra = ["X,0,239,240,4294967295,4294967296,00,-0,-1,1.00,,", "X,"+"a"*1100, "", ","]
        encoded = subprocess.run([str(tmp/"codec")], input="\n".join(lines+extra)+"\n",
                                 text=True, capture_output=True, check=True).stdout.splitlines()
        packets = [bytes.fromhex(s) for s in encoded]
        assert len(packets) == len(lines+extra)
        for packet, line in zip(packets, lines+extra):
            assert decode_datagram(packet)[1:] == [line]
        text_bytes = sum(len(s.encode())+1 for s in lines)
        binary_bytes = sum(len(p)-8 for p in packets[:len(lines)])
        source = tmp/"replay.tsv"
        source.write_text("".join(f"{r['timestamp_unix_ms']-start}\t{s}\n" for r,s in zip(rows,lines)))
        result = subprocess.run([str(tmp/"replay"), str(source)], text=True, capture_output=True, check=True)
        expected = collections.Counter()
        for line in lines:
            for sensor in range(1,10):
                fields = line.split(",",3)
                fields[2] = str(sensor)
                expected[",".join(fields)] += 1
        received = collections.Counter()
        ages = []
        previous = None
        recent = collections.deque()
        recent_bits = 0
        burst_limit_bits = int(120000 * 0.2)
        for row in result.stdout.splitlines():
            time, hex_data = row.split()
            time = int(time)
            data = bytes.fromhex(hex_data)
            if previous is not None:
                last_time, last_data = previous
                assert time-last_time >= 50000, "regular telemetry sent faster than 50 ms slots"
                assert time-last_time >= math.ceil(max(len(last_data)+66,84)*8*1e6/120000)
            previous = time, data
            while recent and time - recent[0][0] >= 200000:
                _, expired_bits = recent.popleft()
                recent_bits -= expired_bits
            packet_bits = max(len(data)+66,84)*8
            assert recent_bits + packet_bits <= burst_limit_bits, "200 ms burst limit exceeded"
            recent.append((time, packet_bits))
            recent_bits += packet_bits
            for line in decode_datagram(data)[1:]:
                if line.startswith("AIRDOS,"):
                    received[line] += 1
                    ages.append(time/1000-int(line.split(",")[1]))
        assert expected == received, "replay lost or changed AIRDOS records"
        print(f"Exact roundtrips: {len(packets)}; text bytes: {text_bytes}; binary record bytes: {binary_bytes}")
        print(f"Record reduction: {1-binary_bytes/text_bytes:.2%}; nine-sensor records delivered: {sum(received.values())}")
        print(f"Maximum simulated delivery delay: {max(ages)} ms")
        print(result.stderr.strip())

if __name__ == "__main__":
    main()
