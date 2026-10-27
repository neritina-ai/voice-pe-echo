from pathlib import Path

import pytest

from voice_pe_echo.cli import parse_args


def test_config_file_and_env(tmp_path, monkeypatch) -> None:
    config = tmp_path / "voice-pe-echo.toml"
    config.write_text('host = "192.168.1.50"\nkey = "abc="\nguard = 1.0\noutput-device = "Speakers"\n', "utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOICE_PE_KEY", raising=False)
    args = parse_args([])
    assert (args.host, args.key, args.guard, args.output_device) == ("192.168.1.50", "abc=", 1.0, "Speakers")

    monkeypatch.setenv("VOICE_PE_KEY", "from-env=")
    assert parse_args([]).key == "from-env="
    assert parse_args(["--key", "cli="]).key == "cli="


def test_unknown_config_key_is_an_error(tmp_path, monkeypatch) -> None:
    (tmp_path / "voice-pe-echo.toml").write_text("hots = 1\n", "utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        parse_args([])


def test_defaults_without_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOICE_PE_KEY", raising=False)
    monkeypatch.delenv("VOICE_PE_HOST", raising=False)
    args = parse_args([])
    assert args.host is None and args.key is None
    assert args.guard == 0.6 and args.silence == 0.8


def test_example_config_is_valid(tmp_path, monkeypatch) -> None:
    example = Path(__file__).parent.parent / "voice-pe-echo.example.toml"
    (tmp_path / "voice-pe-echo.toml").write_text(example.read_text("utf-8"), "utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOICE_PE_KEY", raising=False)
    monkeypatch.delenv("VOICE_PE_HOST", raising=False)
    args = parse_args([])
    assert args.host is None and args.key is None and args.save_dir is None
    assert args.guard == 0.6
