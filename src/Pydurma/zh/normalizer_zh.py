import re
import unicodedata
from typing import Dict, Iterable, Optional

import opencc

from Pydurma.normalizer import Normalizer

# OpenCC configs applied in order. hk2t and tw2t map Hong Kong / Taiwan standard
# forms to the OpenCC standard traditional form (e.g. 為→爲, 眾→衆, 說→説).
#
# Not used by default:
# - jp2t (Japanese shinjitai to traditional): useful for Japanese editions or OCR
#   (仏→佛, 経→經), but it merges characters that are different words in classical
#   Chinese, like 余 ("I") / 餘 ("surplus") or 予 / 豫. Add it with opencc_configs.
# - t2s / s2t (traditional / simplified): they merge characters that are distinct in
#   classical texts (云/雲, 后/後, 干/乾/幹, 里/裏), which would hide real variants.
DEFAULT_OPENCC_CONFIGS = ("hk2t", "tw2t")

# Common variant pairs that the OpenCC configs above don't unify.
DEFAULT_EXTRA_VARIANTS = {
    "敎": "教",
    "淸": "清",
    "呑": "吞",
    "讃": "讚",
    "眞": "真",
    "卽": "即",
    "綫": "線",  # unified by recent OpenCC versions, not by 1.2 (used on Python 3.8)
}

# Characters that are never converted, because OpenCC merges them with a character
# that is a different word in classical Chinese: 台 (pronoun, star name) / 臺 (terrace),
# 核 (kernel) / 覈 (examine), 參 / 蔘, 才 / 纔, and with jp2t 余 / 餘, 予 / 豫, 党 / 黨.
DEFAULT_KEEP_DISTINCT = set("台臺核覈參蔘才纔余餘予豫党黨")

# Z-variants: the same character drawn with a different shape (e.g. 値/值, 絕/絶,
# 恆/恒, 戶/戸). From the Unicode Han Database (Unihan), field kZVariant, Unicode 18.0;
# characters in DEFAULT_KEEP_DISTINCT are left out. Each character is mapped to one
# member of its group (only used for comparison, the output keeps the original text).
# Unihan data: Copyright © Unicode, Inc., Unicode License v3,
# https://www.unicode.org/terms_of_use.html
DEFAULT_Z_VARIANTS = {
    "䎛": "㖈",  # U+439B -> U+3588
    "㦳": "㘽",  # U+39B3 -> U+363D
    "䱎": "䱍",  # U+4C4E -> U+4C4D
    "𣢧": "䶾",  # U+238A7 -> U+4DBE
    "倂": "併",  # U+5002 -> U+4F75
    "值": "値",  # U+503C -> U+5024
    "兑": "兌",  # U+5151 -> U+514C
    "𠮟": "叱",  # U+20B9F -> U+53F1
    "吴": "吳",  # U+5434 -> U+5433
    "呉": "吳",  # U+5449 -> U+5433
    "填": "塡",  # U+586B -> U+5861
    "壿": "墫",  # U+58FF -> U+58AB
    "𡉟": "壯",  # U+2125F -> U+58EF
    "奬": "奨",  # U+596C -> U+5968
    "獎": "奨",  # U+734E -> U+5968
    "娯": "娛",  # U+5A2F -> U+5A1B
    "娱": "娛",  # U+5A31 -> U+5A1B
    "嬀": "媯",  # U+5B00 -> U+5AAF
    "𡠌": "媲",  # U+2180C -> U+5AB2
    "隺": "寉",  # U+96BA -> U+5BC9
    "帲": "帡",  # U+5E32 -> U+5E21
    "𢖽": "志",  # U+225BD -> U+5FD7
    "𢗿": "怽",  # U+225FF -> U+603D
    "恒": "恆",  # U+6052 -> U+6046
    "悦": "悅",  # U+60A6 -> U+6085
    "户": "戶",  # U+6237 -> U+6236
    "戸": "戶",  # U+6238 -> U+6236
    "捝": "挩",  # U+635D -> U+6329
    "插": "挿",  # U+63D2 -> U+633F
    "揷": "挿",  # U+63F7 -> U+633F
    "搖": "揺",  # U+6416 -> U+63FA
    "摇": "揺",  # U+6447 -> U+63FA
    "㩁": "搉",  # U+3A41 -> U+6409
    "敚": "敓",  # U+655A -> U+6553
    "晩": "晚",  # U+6669 -> U+665A
    "㫚": "曶",  # U+3ADA -> U+66F6
    "棁": "梲",  # U+68C1 -> U+68B2
    "樧": "榝",  # U+6A27 -> U+699D
    "㮣": "槩",  # U+3BA3 -> U+69E9
    "涚": "涗",  # U+6D9A -> U+6D97
    "潙": "溈",  # U+6F59 -> U+6E88
    "𤽜": "皌",  # U+24F5C -> U+768C
    "硏": "研",  # U+784F -> U+7814
    "𥑘": "砞",  # U+25458 -> U+781E
    "𥘯": "祙",  # U+2562F -> U+7959
    "税": "稅",  # U+7A0E -> U+7A05
    "𥡴": "稽",  # U+25874 -> U+7A3D
    "𥶉": "籑",  # U+25D89 -> U+7C51
    "𫾟": "籜",  # U+2BF9F -> U+7C5C
    "絶": "絕",  # U+7D76 -> U+7D55
    "絚": "絙",  # U+7D5A -> U+7D59
    "緖": "緒",  # U+7DD6 -> U+7DD2
    "腁": "胼",  # U+8141 -> U+80FC
    "脱": "脫",  # U+8131 -> U+812B
    "茉": "苿",  # U+8309 -> U+82FF
    "蔿": "蒍",  # U+853F -> U+848D
    "虁": "蘷",  # U+8641 -> U+8637
    "蜕": "蛻",  # U+8715 -> U+86FB
    "詽": "訮",  # U+8A7D -> U+8A2E
    "説": "說",  # U+8AAC -> U+8AAA
    "謡": "謠",  # U+8B21 -> U+8B20
    "豣": "豜",  # U+8C63 -> U+8C5C
    "跺": "跥",  # U+8DFA -> U+8DE5
    "躛": "躗",  # U+8E9B -> U+8E97
    "躲": "躱",  # U+8EB2 -> U+8EB1
    "輧": "軿",  # U+8F27 -> U+8EFF
    "𨓜": "逸",  # U+284DC -> U+9038
    "郞": "郎",  # U+90DE -> U+90CE
    "鄉": "郷",  # U+9109 -> U+90F7
    "鄕": "郷",  # U+9115 -> U+90F7
    "鋭": "銳",  # U+92ED -> U+92B3
    "鎮": "鎭",  # U+93AE -> U+93AD
    "𨮺": "鑙",  # U+28BBA -> U+9459
    "𨺓": "隆",  # U+28E93 -> U+9686
    "隸": "隷",  # U+96B8 -> U+96B7
    "𫸔": "頲",  # U+2BE14 -> U+9832
    "飲": "飮",  # U+98F2 -> U+98EE
    "黒": "黑",  # U+9ED2 -> U+9ED1
    "𢬎": "𢫮",  # U+22B0E -> U+22AEE
    "𬄺": "𣟃",  # U+2C13A -> U+237C3
    "𱽨": "𦰥",  # U+31F68 -> U+26C25
    "𩿲": "𩿣",  # U+29FF2 -> U+29FE3
    "𱽌": "𬻋",  # U+31F4C -> U+2CECB
}

WHITESPACE_RE = re.compile(r"\s+")
# punctuation and other non-word characters (including variation selectors)
NON_WORD_RE = re.compile(r"[\W_]+")


class ChineseNormalizer(Normalizer):
    """
    Normalizer for Chinese (mostly classical / Buddhist Chinese).

    The token text itself is never changed (normalize_always is the identity), so the
    output keeps the original characters. Normalization is only applied to the form
    used for comparison:

    - NFKC: full-width / half-width forms and CJK compatibility ideographs
    - removal of whitespace
    - variant characters (異體字) unified with OpenCC, a small extra table and the
      Unihan z-variants, except for the characters in keep_distinct
    - removal of punctuation, except in tokens that only have punctuation (so that
      punctuation tokens can still be compared and voted on)
    """

    def __init__(
        self,
        opencc_configs: Iterable[str] = DEFAULT_OPENCC_CONFIGS,
        extra_variants: Optional[Dict[str, str]] = None,
        keep_distinct: Optional[Iterable[str]] = None,
        z_variants: Optional[Dict[str, str]] = None,
    ):
        """
        opencc_configs: OpenCC config names applied in order. Add "jp2t" for Japanese
                        editions or OCR, use ["t2s"] only if witnesses mix simplified
                        and traditional script.
        extra_variants: character → character mapping applied after OpenCC.
                        Defaults to DEFAULT_EXTRA_VARIANTS.
        keep_distinct: characters that are never converted. Defaults to DEFAULT_KEEP_DISTINCT.
        z_variants: character → character mapping of z-variants (same character, different
                    shape). Defaults to DEFAULT_Z_VARIANTS; pass {} to turn it off.
        """
        self.converters = [opencc.OpenCC(config) for config in opencc_configs]
        self.extra_variants = DEFAULT_EXTRA_VARIANTS if extra_variants is None else extra_variants
        self.keep_distinct = DEFAULT_KEEP_DISTINCT if keep_distinct is None else set(keep_distinct)
        self.z_variants = DEFAULT_Z_VARIANTS if z_variants is None else z_variants
        self._cache: Dict[str, str] = {}

    def normalize_always(self, s: str) -> str:
        return s

    def normalize_char(self, c: str) -> str:
        if c in self.keep_distinct:
            return c
        # z-variants before and after OpenCC, so that two z-variants always end up
        # the same even if OpenCC converts one of them
        c = self.z_variants.get(c, c)
        for converter in self.converters:
            c = converter.convert(c)
        c = self.extra_variants.get(c, c)
        return self.z_variants.get(c, c)

    def normalize_for_comparison(self, s: str) -> str:
        res = self._cache.get(s)
        if res is not None:
            return res
        res = WHITESPACE_RE.sub("", unicodedata.normalize("NFKC", s))
        without_punctuation = NON_WORD_RE.sub("", res)
        if without_punctuation:
            res = without_punctuation
        res = "".join(self.normalize_char(c) for c in res)
        self._cache[s] = res
        return res

    def normalize_pre_token_diff(self, s: str) -> str:
        return self.normalize_for_comparison(s)

    def normalize_pre_token_comparison(self, s: str) -> str:
        return self.normalize_for_comparison(s)
