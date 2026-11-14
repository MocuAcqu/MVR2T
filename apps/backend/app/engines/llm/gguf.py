"""讀取 GGUF 檔案開頭的中繼資料（只讀需要的鍵，不載入模型）。

用途：GPU 記憶體不夠放下整個模型時，要知道模型有幾層（`<arch>.block_count`）才能決定放幾層到 GPU（§5.4）。
格式：https://github.com/ggml-org/ggml/blob/master/docs/gguf.md（v2／v3，小端序）。
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO

# GGUF 值的型別
_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_STRING, _ARRAY = 8, 9


class GgufError(Exception):
    pass


def _read(f: BinaryIO, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise GgufError("檔案提早結束")
    return struct.unpack(fmt, data)[0]


def _string(f: BinaryIO) -> str:
    n = _read(f, "<Q")
    if n > 1 << 24:
        raise GgufError("字串長度不合理")
    return f.read(n).decode("utf-8", "replace")


def _value(f: BinaryIO, vtype: int, keep: bool) -> Any:
    if vtype in _SCALAR:
        return _read(f, _SCALAR[vtype])
    if vtype == _STRING:
        return _string(f)
    if vtype == _ARRAY:
        etype, count = _read(f, "<I"), _read(f, "<Q")
        if etype in _SCALAR and not keep:  # 例如 tokenizer 的大型陣列：直接跳過
            f.seek(struct.calcsize(_SCALAR[etype]) * count, 1)
            return None
        items = [_value(f, etype, keep) for _ in range(count)]
        return items if keep else None
    raise GgufError(f"未知的型別 {vtype}")


def read_metadata(path: Path, wanted: set[str] | None = None) -> dict[str, Any]:
    """回傳中繼資料；wanted 指定時只保留這些鍵，而且找齊就停止（不必讀完整個 tokenizer）。"""
    out: dict[str, Any] = {}
    with path.open("rb") as f:
        if f.read(4) != b"GGUF":
            raise GgufError("不是 GGUF 檔案")
        version = _read(f, "<I")
        if version not in (2, 3):
            raise GgufError(f"不支援的 GGUF 版本 {version}")
        _read(f, "<Q")  # tensor 數量
        kv_count = _read(f, "<Q")
        for _ in range(kv_count):
            key = _string(f)
            vtype = _read(f, "<I")
            keep = wanted is None or key in wanted
            value = _value(f, vtype, keep)
            if keep:
                out[key] = value
            if wanted is not None and wanted <= out.keys():
                break
    return out


def block_count(path: Path) -> int | None:
    """模型的層數；讀不到時 None。"""
    try:
        arch = read_metadata(path, {"general.architecture"}).get("general.architecture")
        if not arch:
            return None
        n = read_metadata(path, {f"{arch}.block_count"}).get(f"{arch}.block_count")
        return int(n) if n else None
    except (OSError, GgufError, struct.error, ValueError):
        return None


def kv_bytes_per_token(path: Path) -> int | None:
    """KV cache 每個 token 約用多少 bytes（f16）。混合架構（例如 Qwen3.5 每 4 層才有一層完整注意力）只算有 KV 的層。"""
    try:
        arch = read_metadata(path, {"general.architecture"}).get("general.architecture")
        if not arch:
            return None
        keys = {f"{arch}.{k}" for k in ("block_count", "attention.head_count_kv", "attention.key_length", "attention.value_length",
                                         "attention.head_count", "embedding_length", "full_attention_interval")}
        meta = {k.split(".", 1)[1]: v for k, v in read_metadata(path, keys).items()}
        layers = int(meta["block_count"])
        heads_kv = meta.get("attention.head_count_kv") or meta.get("attention.head_count")
        if isinstance(heads_kv, list):
            heads_kv = max(heads_kv)
        key_len = meta.get("attention.key_length") or (int(meta["embedding_length"]) // int(meta.get("attention.head_count") or 1))
        value_len = meta.get("attention.value_length") or key_len
        interval = int(meta.get("full_attention_interval") or 1)
        kv_layers = max(1, layers // max(1, interval))
        return int(kv_layers * int(heads_kv) * (int(key_len) + int(value_len)) * 2)
    except (OSError, GgufError, struct.error, ValueError, KeyError, TypeError):
        return None
