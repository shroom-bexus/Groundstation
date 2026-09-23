import unittest
from binary_telemetry import decode_datagram

class BinaryTelemetryTests(unittest.TestCase):
    def packet(self, body):
        return b'SHB1\x01\0\0\0'+len(body).to_bytes(2,'little')+body

    def test_golden(self):
        # AIRDOS,123,1,$E,54450,65
        p=self.packet(b'\x01\xf2\0\x7b\x01\xf2\x01\xf0\xb2\xd4\0\0\x41')
        self.assertEqual(decode_datagram(p),['SEQ,1','AIRDOS,123,1,$E,54450,65'])

    def test_raw_and_legacy(self):
        self.assertEqual(decode_datagram(self.packet(b'\0RTC,1,UNKNOWN')),['SEQ,1','RTC,1,UNKNOWN'])
        self.assertEqual(decode_datagram(b'ACK,5,OK\n'),['ACK,5,OK'])
        self.assertEqual(decode_datagram(b'SEQ,2\nPADS,0,293.15,100000\n'),['SEQ,2','PADS,0,293.15,100000'])

    def test_long_airdos_record(self):
        line = b'AIRDOS,4294967295,9,$X,' + b'a' * 1000
        self.assertLessEqual(len(line), 1151)
        self.assertEqual(
            decode_datagram(self.packet(b'\0' + line)),
            ['SEQ,1', line.decode('ascii')]
        )

    def test_corruption(self):
        for body in [b'',b'\2',b'\1',b'\1\xf0',b'\1\xf1',b'\1\xf1\x05\0ab',b'\1\xf2\xff',b'\0a\nb',b'\0a\0b',b'\1'+b'\xef'*1200]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                decode_datagram(self.packet(body))
        for data in [b'SHB2'+b'\0'*10,b'SHB1',self.packet(b'\0okay')+b'\x02']:
            with self.assertRaises(ValueError): decode_datagram(data)

if __name__=='__main__': unittest.main()
