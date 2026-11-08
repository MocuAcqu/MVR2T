"""模型登錄表：模型 ID、版本、下載來源與檔案雜湊集中在這裡（PROJECT_SPEC 第 16 條、§7.2、§17）。

- 一律固定 Hugging Face 的 commit（revision），不追最新版。
- 每個檔案都有雜湊：大檔（LFS / Xet）用 SHA-256；小檔（設定檔）用 Git blob SHA-1（Hugging Face API 提供的 blobId）。
  下載後逐一驗證，確保離線使用的檔案與官方發布的一模一樣。
- 模型放在 <userData>/models/<kind>/<id>/（規格 §7.3），驗證成功後寫入 .mvr2t-model.json 作為「已安裝」標記。

更新模型版本：改 revision 與 files（可用 https://huggingface.co/api/models/<repo>?blobs=true 取得大小與雜湊）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ModelKind = Literal["asr", "aligner", "llm"]
HashAlgo = Literal["sha256", "git-sha1"]


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    algo: HashAlgo
    digest: str


@dataclass(frozen=True)
class ModelSpec:
    id: str  # 本機資料夾名稱
    kind: ModelKind
    display_name: str
    role: str  # 介面顯示的用途
    repo: str  # 官方來源
    revision: str  # 固定的 commit
    license: str
    files: tuple[ModelFile, ...] = ()
    #: 說明哪個 Phase 才會實作（尚未提供下載的模型）
    available_from_phase: int | None = None

    @property
    def size_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def downloadable(self) -> bool:
        return bool(self.files) and self.available_from_phase is None

    def local_dir(self, models_root: Path) -> Path:
        return models_root / self.kind / self.id


QWEN3_ASR_0_6B = ModelSpec(
    id="qwen3-asr-0.6b",
    kind="asr",
    display_name="Qwen3-ASR 0.6B",
    role="語音辨識",
    repo="Qwen/Qwen3-ASR-0.6B-hf",
    revision="7f1569a48a89f3e3f4dc3a5c9d28bddd903bc76c",
    license="Apache-2.0",
    files=(
        ModelFile("model.safetensors", 1564928088, "sha256", "d3f212dd20abecd315d830bc54ae3865e56ebfc3276484e57b771288ba27fd35"),
        ModelFile("tokenizer.json", 11429653, "sha256", "fe1fad59be22a41ee293363fcf95fdedbc7c93f3b49270b1d2e18bd1399a7a05"),
        ModelFile("config.json", 2398, "git-sha1", "3b4221f651b59ec21f545e5852b4d6cb23420b09"),
        ModelFile("generation_config.json", 165, "git-sha1", "3ed98c80087572bad932a83279c5602e58bbfc5c"),
        ModelFile("processor_config.json", 487, "git-sha1", "a07dff48032bed341260501d6688036c6fd7f3ef"),
        ModelFile("tokenizer_config.json", 998, "git-sha1", "aa62b6c06ab8a704dc0895420fb1d2515954a49c"),
        ModelFile("chat_template.jinja", 1434, "git-sha1", "491fff331513a97316daf53591c7b9b9da53ef8c"),
    ),
)

QWEN3_FORCED_ALIGNER_0_6B = ModelSpec(
    id="qwen3-forcedaligner-0.6b",
    kind="aligner",
    display_name="Qwen3-ForcedAligner 0.6B",
    role="時間戳記對齊",
    repo="Qwen/Qwen3-ForcedAligner-0.6B-hf",
    revision="c07281df297b9905d24a508279258cccf987a064",
    license="Apache-2.0",
    files=(
        ModelFile("model.safetensors", 1835545960, "sha256", "00568245ceca5af1991d28562a75fe1ddc9bfeb041c27fda66947ea05c47fb86"),
        ModelFile("tokenizer.json", 11429842, "sha256", "cadfb9cbd9ff8f4e309075ec6a71b063295ff796afb4b5dbc0fd2873fbb301f2"),
        ModelFile("config.json", 248029, "git-sha1", "74b91ca23584bdebd82ffaaeb21f72444baa2dd8"),
        ModelFile("processor_config.json", 487, "git-sha1", "a07dff48032bed341260501d6688036c6fd7f3ef"),
        ModelFile("tokenizer_config.json", 998, "git-sha1", "aa62b6c06ab8a704dc0895420fb1d2515954a49c"),
        ModelFile("chat_template.jinja", 551, "git-sha1", "1d6020e0ee6f66499d674a3fc2bbae5a99482c0e"),
    ),
)

QWEN3_4B_Q4_K_M = ModelSpec(
    id="qwen3-4b-q4_k_m",
    kind="llm",
    display_name="Qwen3-4B Q4_K_M",
    role="摘要與心智圖",
    repo="Qwen/Qwen3-4B-GGUF",
    revision="",
    license="Apache-2.0",
    available_from_phase=6,
)

ALL_MODELS: tuple[ModelSpec, ...] = (QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B, QWEN3_4B_Q4_K_M)
BY_ID = {m.id: m for m in ALL_MODELS}

# 時間戳記對齊模型支援的語言（Qwen3-ASR 回報的英文名稱）。其餘語言退回切段層級的時間。
ALIGNER_LANGUAGES = frozenset(
    {"Chinese", "English", "Cantonese", "French", "German", "Italian", "Japanese", "Korean", "Portuguese", "Russian", "Spanish"}
)
