import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STOPWORDS = {"bank", "eks", "ex", "tbk", "persero"}

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")
_WORD_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _normalize(value: str) -> str:
    """Lowercase + buang aksen/tanda baca agar pencocokan konsisten."""
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode()
    return _WORD_SPLIT.sub(" ", text.lower()).strip()


class DataLoader:
    def __init__(self, data_dir: Path | str = Path("app/data")) -> None:
        self.data_dir = Path(data_dir)
        self.bank_contacts: List[Dict[str, Any]] = []
        self.knowledge_base: List[Dict[str, Any]] = []
        self._bank_aliases: List[Tuple[re.Pattern[str], str, int, Dict[str, Any]]] = []
        self._load_data()
        self._build_bank_index()

    def _load_data(self) -> None:
        try:
            bank_file = self.data_dir / "Bank_Call_Senter_Final.json"
            if bank_file.exists():
                raw = json.loads(bank_file.read_text("utf-8"))
                if isinstance(raw, list):
                    self.bank_contacts = [
                        item
                        for item in raw
                        if isinstance(item, dict) and item.get("name")
                    ]
                else:
                    logger.error("Format %s tidak valid (harus list).", bank_file)
            else:
                logger.warning("File tidak ditemukan: %s", bank_file)

            kb_file = self.data_dir / "knowledge_base_cegahscam.json"
            if kb_file.exists():
                kb_data = json.loads(kb_file.read_text("utf-8"))
                if isinstance(kb_data, dict):
                    self.knowledge_base = kb_data.get("scam_knowledge_base", [])
                else:
                    logger.error("Format %s tidak valid (harus object).", kb_file)
            else:
                logger.warning("File tidak ditemukan: %s", kb_file)

        except Exception as e:
            logger.error("Gagal memuat data statis: %s", e)

    def _build_bank_index(self) -> None:
        """Precompute alias bank supaya pencocokan per request murah."""
        seen: set[Tuple[str, int]] = set()
        for order, bank in enumerate(self.bank_contacts):
            for alias in sorted(self._aliases_for(bank)):
                if (alias, order) in seen:
                    continue
                seen.add((alias, order))
                pattern = re.compile(
                    r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
                )
                self._bank_aliases.append((pattern, alias, order, bank))

    @staticmethod
    def _aliases_for(bank: Dict[str, Any]) -> set[str]:
        name = str(bank.get("name", ""))
        aliases: set[str] = {_normalize(name)}

        for inner in re.findall(r"\(([^)]*)\)", name):
            aliases.add(_normalize(inner))
            words = [
                word
                for word in _WORD_TOKEN.findall(inner)
                if word.lower() not in {"eks", "ex"}
            ]
            if len(words) >= 2:
                aliases.add("".join(word[0] for word in words).lower())

        normalized = _normalize(name)
        if normalized.startswith("bank "):
            aliases.add(normalized[len("bank ") :])

        for token in _WORD_TOKEN.findall(name):
            if len(token) >= 4 and token.isupper() and token.lower() not in _STOPWORDS:
                aliases.add(_normalize(token))

        explicit = bank.get("aliases")
        if isinstance(explicit, list):
            aliases.update(
                _normalize(item) for item in explicit if isinstance(item, str)
            )

        return {alias for alias in aliases if alias and alias not in _STOPWORDS}

    def _best_match(self, texts: Tuple[str, ...]) -> Optional[Tuple[Dict[str, Any], str]]:
        haystack = " ".join(_normalize(text) for text in texts if text and str(text).strip())
        if not haystack:
            return None

        per_bank: Dict[int, Tuple[Tuple[Any, ...], str, Dict[str, Any]]] = {}
        candidate_names: set[str] = set()

        for pattern, alias, order, bank in self._bank_aliases:
            match = pattern.search(haystack)
            if not match:
                continue

            rank = (
                0 if haystack == alias else 1,
                -len(alias.split()),
                -len(alias),
                match.start(),
                len(str(bank.get("name", ""))),
                order,
            )

            current = per_bank.get(order)
            if current is None or rank < current[0]:
                per_bank[order] = (rank, alias, bank)
            candidate_names.add(str(bank.get("name")))

        if not per_bank:
            return None

        best_rank, best_alias, best_bank = min(
            per_bank.values(), key=lambda item: item[0]
        )

        if len(candidate_names) > 1:
            logger.info(
                "Beberapa bank terdeteksi (%s); dipilih %s via alias '%s'.",
                ", ".join(sorted(candidate_names)),
                best_bank.get("name"),
                best_alias,
            )
        else:
            logger.debug(
                "Bank terdeteksi: %s via alias '%s'.", best_bank.get("name"), best_alias
            )
        return best_bank, best_alias

    def match_bank(self, *texts: str) -> Optional[Dict[str, Any]]:
        """Kembalikan entri bank paling cocok dari whitelist call center."""
        found = self._best_match(texts)
        return found[0] if found else None

    def official_contact_for(self, *texts: str) -> Optional[Dict[str, str]]:
        """Bangun official_contact hanya dari bank yang terdaftar di data statis."""
        found = self._best_match(texts)
        if not found:
            return None

        bank, alias = found
        call = bank.get("call")
        if call is None:
            logger.warning(
                "Bank %s cocok via alias '%s' tapi tidak punya nomor call center.",
                bank.get("name"),
                alias,
            )
            return None

        return {"name": str(bank.get("name")), "phone": str(call)}

    def find_bank_contact(self, bank_name: str) -> Dict[str, Any] | None:
        """Kompatibilitas: cari entri bank berdasarkan nama (case-insensitive)."""
        return self.match_bank(bank_name)
