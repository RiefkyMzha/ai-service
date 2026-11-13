import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STOPWORDS = {"bank", "eks", "ex", "tbk", "persero"}
_SKIP_TOKENS = _STOPWORDS | {"eks", "bpr", "bpd", "tbk", "ltd"}
_BANK_PREFIX_REQUIRED = {
    "mas",
    "jago",
    "mega",
    "raya",
    "index",
    "capital",
    "prima",
    "bumi",
    "jasa",
    "ina",
    "aceh",
    "papua",
    "bali",
    "jakarta",
    "banten",
    "yogyakarta",
    "jateng",
    "jatim",
    "sumut",
    "kalbar",
    "kalteng",
    "kaltimtara",
    "sulselbar",
    "sumselbabel",
    "ntb",
    "diy",
    "dki",
}

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
        self._kb_index: List[Tuple[str, set[str], str]] = []
        self._load_data()
        self._build_bank_index()
        self._build_kb_index()

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
    def _add_safe_alias(aliases: set[str], candidate: str) -> None:
        cleaned = candidate.strip()
        if not cleaned or cleaned in _STOPWORDS:
            return
        if len(cleaned.split()) == 1 and cleaned in _BANK_PREFIX_REQUIRED:
            return
        aliases.add(cleaned)

    @classmethod
    def _aliases_for(cls, bank: Dict[str, Any]) -> set[str]:
        name = str(bank.get("name", ""))
        aliases: set[str] = set()
        cls._add_safe_alias(aliases, _normalize(name))

        outer_raw = re.sub(r"\([^)]*\)", "", name).strip()
        for part in outer_raw.split("/"):
            norm_part = _normalize(part)
            cls._add_safe_alias(aliases, norm_part)
            if norm_part.startswith("bank "):
                cls._add_safe_alias(aliases, norm_part[len("bank ") :])

        for inner in re.findall(r"\(([^)]*)\)", name):
            norm_inner = _normalize(inner)
            if not norm_inner:
                continue
            cls._add_safe_alias(aliases, norm_inner)
            if norm_inner.startswith(("eks ", "ex ")):
                cls._add_safe_alias(aliases, re.sub(r"^(?:eks|ex)\s+", "", norm_inner))
            else:
                if norm_inner.startswith("bank "):
                    cls._add_safe_alias(aliases, norm_inner[len("bank ") :])
                words = [
                    word
                    for word in _WORD_TOKEN.findall(inner)
                    if word.lower() not in {"eks", "ex"}
                ]
                if len(words) >= 3:
                    cls._add_safe_alias(
                        aliases, "".join(word[0] for word in words).lower()
                    )

        if "syariah" not in outer_raw.lower() and "digital" not in outer_raw.lower():
            for token in _WORD_TOKEN.findall(outer_raw):
                if (
                    len(token) >= 3
                    and token.isupper()
                    and token.lower() not in _SKIP_TOKENS
                ):
                    cls._add_safe_alias(aliases, _normalize(token))

        explicit = bank.get("aliases")
        if isinstance(explicit, list):
            for item in explicit:
                if isinstance(item, str):
                    norm_item = _normalize(item)
                    if norm_item and norm_item not in _STOPWORDS:
                        aliases.add(norm_item)

        return aliases

    def _best_match(
        self,
        texts: Tuple[str, ...],
        exclude_names: Optional[set[str]] = None,
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        haystack = " ".join(_normalize(text) for text in texts if text and str(text).strip())
        if not haystack:
            return None

        per_bank: Dict[int, Tuple[Tuple[Any, ...], str, Dict[str, Any]]] = {}
        candidate_names: set[str] = set()

        for pattern, alias, order, bank in self._bank_aliases:
            if exclude_names and bank.get("name") in exclude_names:
                continue
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

    def match_bank(
        self,
        *texts: str,
        exclude_names: Optional[set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Kembalikan entri bank paling cocok dari whitelist call center."""
        found = self._best_match(texts, exclude_names=exclude_names)
        return found[0] if found else None

    def match_banks(
        self,
        *texts: str,
        limit: int = 3,
        exclude_names: Optional[set[str]] = None,
        require_call: bool = False,
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []

        results: List[Dict[str, Any]] = []
        seen_orders: set[int] = set()

        for text in texts:
            haystack = _normalize(str(text)) if text else ""
            if not haystack:
                continue

            raw_matches: List[
                Tuple[Tuple[Any, ...], int, int, str, int, Dict[str, Any]]
            ] = []
            for pattern, alias, order, bank in self._bank_aliases:
                if exclude_names and bank.get("name") in exclude_names:
                    continue
                if require_call and bank.get("call") is None:
                    continue
                for match in pattern.finditer(haystack):
                    start, end = match.start(), match.end()
                    spec_key = (
                        -len(alias.split()),
                        -len(alias),
                        start,
                        len(str(bank.get("name", ""))),
                        order,
                    )
                    raw_matches.append((spec_key, start, end, alias, order, bank))

            raw_matches.sort(key=lambda item: item[0])

            claimed_spans: List[Tuple[int, int]] = []
            accepted: List[Tuple[Tuple[Any, ...], int, Dict[str, Any]]] = []
            for _, start, end, alias, order, bank in raw_matches:
                if any(start < c_end and end > c_start for c_start, c_end in claimed_spans):
                    continue
                claimed_spans.append((start, end))
                rank = (
                    0 if haystack == alias else 1,
                    start,
                    -len(alias.split()),
                    -len(alias),
                    order,
                )
                accepted.append((rank, order, bank))

            accepted.sort(key=lambda item: item[0])
            for _, order, bank in accepted:
                if order in seen_orders:
                    continue
                seen_orders.add(order)
                results.append(bank)
                if len(results) >= limit:
                    return results

        return results

    def official_contact_for(
        self,
        *texts: str,
        exclude_names: Optional[set[str]] = None,
    ) -> Optional[Dict[str, str]]:
        """Bangun official_contact hanya dari bank yang terdaftar di data statis."""
        found = self._best_match(texts, exclude_names=exclude_names)
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

    def official_contacts_for(
        self,
        *texts: str,
        limit: int = 3,
        exclude_names: Optional[set[str]] = None,
    ) -> List[Dict[str, str]]:
        banks = self.match_banks(
            *texts,
            limit=limit,
            exclude_names=exclude_names,
            require_call=True,
        )
        return [
            {"name": str(bank.get("name")), "phone": str(bank.get("call"))}
            for bank in banks
        ]

    def find_bank_contact(self, bank_name: str) -> Dict[str, Any] | None:
        """Kompatibilitas: cari entri bank berdasarkan nama (case-insensitive)."""
        return self.match_bank(bank_name)

    def _build_kb_index(self) -> None:
        grouped_keywords: Dict[str, set[str]] = {}
        grouped_sop: Dict[str, str] = {}
        for item in self.knowledge_base:
            if not isinstance(item, dict):
                continue
            category = str(item.get("kategori_pola") or "").strip()
            if not category or category == "Bukan Scam (Percakapan Normal)":
                continue
            keywords = item.get("keywords_terkait") or []
            if not isinstance(keywords, list):
                continue
            norm_kws = {
                _normalize(str(kw))
                for kw in keywords
                if isinstance(kw, str) and _normalize(str(kw))
            }
            if not norm_kws:
                continue
            grouped_keywords.setdefault(category, set()).update(norm_kws)
            sop = str(item.get("sop_mitigasi") or "").strip()
            if sop and category not in grouped_sop:
                grouped_sop[category] = sop

        self._kb_index = [
            (cat, kws, grouped_sop.get(cat, ""))
            for cat, kws in grouped_keywords.items()
        ]

    def match_knowledge_base(
        self,
        text: str,
        min_keywords: int = 3,
    ) -> List[Dict[str, Any]]:
        norm_text = _normalize(text)
        if not norm_text:
            return []
        words = set(norm_text.split())
        matches: List[Dict[str, Any]] = []
        for category, kws, sop in self._kb_index:
            matched = [
                kw
                for kw in kws
                if (kw in words if " " not in kw else kw in norm_text)
            ]
            if len(matched) >= min_keywords:
                matches.append(
                    {
                        "kategori_pola": category,
                        "matched_keywords": sorted(matched),
                        "sop_mitigasi": sop,
                    }
                )
        matches.sort(key=lambda item: (-len(item["matched_keywords"]), item["kategori_pola"]))
        return matches
