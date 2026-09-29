"""tools/generate_music_beds.py: the parts that cost nothing (the WAV repair and the dry run)."""
import importlib.util
import io
import os
import struct
import sys
import wave

_PATH = os.path.join(os.path.dirname(__file__), "..", "tools", "generate_music_beds.py")
_spec = importlib.util.spec_from_file_location("generate_music_beds", _PATH)
beds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(beds)


def _wav(pcm: bytes, rate: int = 48000, channels: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def test_the_nested_wav_header_is_removed():
    """Lyria's data chunk opens with a second WAV header, which would play as a click."""
    pcm = struct.pack("<8h", *range(8))
    nested = _wav(_wav(pcm))  # a WAV whose audio is itself a whole WAV file
    with wave.open(io.BytesIO(beds.clean_wav(nested)), "rb") as w:
        assert (w.getnchannels(), w.getframerate()) == (2, 48000)
        assert w.readframes(w.getnframes()) == pcm


def test_a_plain_wav_is_left_alone():
    plain = _wav(b"\x00\x01" * 8)
    assert beds.clean_wav(plain) == plain


def test_without_yes_nothing_is_generated(monkeypatch, tmp_path, capsys):
    """The tool is billed: the default run must only print the plan."""
    monkeypatch.setitem(sys.modules, "google.auth", None)  # any import of it would fail
    assert beds.main([str(tmp_path)]) == 0
    assert "Nothing generated" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())
