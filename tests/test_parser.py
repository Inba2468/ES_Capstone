"""
tests/test_parser.py
====================
Unit tests for core/protocol_parser.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.protocol_parser import ProtocolParser

p = ProtocolParser()

# ── CHAT tests ────────────────────────────────────────────────────────────────

def test_chat_with_sender():
    r = p.parse("CHAT:NODE-2:Hello command, copy?")
    assert r is not None
    assert r['type'] == 'CHAT'
    assert r['sender'] == 'NODE-2'
    assert r['text'] == 'Hello command, copy?'

def test_chat_no_sender():
    r = p.parse("CHAT:All clear sector 9")
    assert r is not None
    assert r['type'] == 'CHAT'
    assert r['sender'] == 'NODE'
    assert r['text'] == 'All clear sector 9'

def test_chat_case_insensitive():
    r = p.parse("chat:NODE-3:Moving north")
    assert r is not None
    assert r['type'] == 'CHAT'

# ── SYS tests ─────────────────────────────────────────────────────────────────

def test_sys_valid():
    r = p.parse("SYS:13.08270,80.27070,28.5,65.0,450,800")
    assert r is not None
    assert r['type'] == 'SYS'
    assert abs(r['lat'] - 13.0827) < 0.001
    assert abs(r['temp'] - 28.5) < 0.01
    assert r['smoke'] == 450
    assert r['water'] == 800

def test_sys_negative_lat():
    r = p.parse("SYS:-33.86785,151.20732,22.0,50.0,100,200")
    assert r is not None
    assert r['lat'] < 0

def test_sys_missing_fields():
    r = p.parse("SYS:13.0827,80.2707,28.5")
    assert r is None   # malformed → None

# ── SOS tests ─────────────────────────────────────────────────────────────────

def test_sos_basic():
    r = p.parse("SOS:13.08270,80.27070,HELP")
    assert r is not None
    assert r['type'] == 'SOS'
    assert r['sender'] == 'UNKNOWN'

def test_sos_with_sender():
    r = p.parse("SOS:13.08270,80.27070,HELP:NODE-3")
    assert r is not None
    assert r['type'] == 'SOS'
    assert r['sender'] == 'NODE-3'
    assert abs(r['lat'] - 13.0827) < 0.001

# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_string():
    assert p.parse("") is None

def test_garbage():
    assert p.parse("GARBAGE:123:abc") is None

def test_whitespace():
    r = p.parse("  CHAT:NODE-1:Message with spaces  ")
    assert r is not None
    assert r['type'] == 'CHAT'

# ── Builders ──────────────────────────────────────────────────────────────────

def test_build_chat():
    s = ProtocolParser.build_chat("hello", "CMD")
    assert s == "CHAT:CMD:hello"

def test_build_sos_ack():
    s = ProtocolParser.build_sos_ack(13.08270, 80.27070)
    assert s.startswith("ACK:SOS:")


if __name__ == '__main__':
    tests = [
        test_chat_with_sender, test_chat_no_sender, test_chat_case_insensitive,
        test_sys_valid, test_sys_negative_lat, test_sys_missing_fields,
        test_sos_basic, test_sos_with_sender,
        test_empty_string, test_garbage, test_whitespace,
        test_build_chat, test_build_sos_ack,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS]  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL]  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} tests passed")
