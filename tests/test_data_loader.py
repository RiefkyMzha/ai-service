import json

import pytest

from app.core.data_loader import DataLoader


@pytest.fixture(scope="module")
def loader() -> DataLoader:
    return DataLoader()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("bank mandiri", "Bank Mandiri"),
        ("mandiri", "Bank Mandiri"),
        ("mandiri taspen", "Bank Mandiri Taspen"),
        ("bca", "Bank BCA (Bank Central Asia)"),
        ("bca syariah", "Bank BCA Syariah"),
        ("bri", "Bank BRI (Bank Rakyat Indonesia)"),
        ("bca dan bri", "Bank BCA (Bank Central Asia)"),
        (
            "saya ditipu mengaku BRI lalu transfer ke BCA",
            "Bank BRI (Bank Rakyat Indonesia)",
        ),
        ("bank gaib", None),
        ("", None),
    ],
)
def test_match_bank_ranking(loader: DataLoader, text: str, expected: str | None):
    bank = loader.match_bank(text)
    assert (bank or {}).get("name") == expected


def test_match_bank_handles_url_and_dashes(loader: DataLoader):
    bank = loader.match_bank("klik https://bca-verifikasi.xyz sekarang")
    assert bank is not None
    assert bank["name"] == "Bank BCA (Bank Central Asia)"


def test_official_contact_for_returns_phone_string(loader: DataLoader):
    contact = loader.official_contact_for("Halo, ini BCA. Akun Anda diblokir.")
    assert contact == {"name": "Bank BCA (Bank Central Asia)", "phone": "1500888"}


def test_official_contact_for_unknown_bank(loader: DataLoader):
    assert loader.official_contact_for("Bank Gaib Internasional") is None


def test_find_bank_contact_backward_compatible(loader: DataLoader):
    assert loader.find_bank_contact("bca") == loader.match_bank("bca")


def test_explicit_aliases_are_supported(tmp_path):
    (tmp_path / "Bank_Call_Senter_Final.json").write_text(
        json.dumps(
            [
                {
                    "name": "Bank Contoh (Bank Contoh Indonesia)",
                    "call": 1500123,
                    "aliases": ["bankcontoh", "bci"],
                }
            ]
        ),
        encoding="utf-8",
    )

    loader = DataLoader(data_dir=tmp_path)
    assert loader.match_bank("hubungi bci sekarang")["name"] == (
        "Bank Contoh (Bank Contoh Indonesia)"
    )
    assert loader.official_contact_for("bci") == {
        "name": "Bank Contoh (Bank Contoh Indonesia)",
        "phone": "1500123",
    }


def test_missing_data_files_do_not_crash(tmp_path):
    loader = DataLoader(data_dir=tmp_path)
    assert loader.bank_contacts == []
    assert loader.match_bank("bca") is None


def test_match_knowledge_base_requires_min_three_keywords(loader: DataLoader):
    assert loader.match_knowledge_base("Selamat anda dapat hadiah", min_keywords=3) == []
    matches = loader.match_knowledge_base(
        "Selamat anda pemenang hadiah undian resmi", min_keywords=3
    )
    assert len(matches) >= 1
    assert matches[0]["kategori_pola"] == "Undian Palsu (Fake Reward)"
    assert len(matches[0]["matched_keywords"]) >= 3


def test_match_knowledge_base_ignores_normal_category(loader: DataLoader):
    matches = loader.match_knowledge_base(
        "Kita ngobrol biasa saja untuk bagi info", min_keywords=3
    )
    assert matches == []
