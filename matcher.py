"""
프롬프트 ↔ 이미지 매칭 엔진 (100% 로컬)

점수 = CLIP 이미지-장면 유사도(주) + 인물 옷차림 유사도 + 파일명 캡션 TF-IDF 유사도(보조)
배정 = 번호마다 (이미지 수 / 프롬프트 수)장씩 슬롯을 두고 헝가리안 알고리즘으로 전역 최적 배정.
       기대 장수를 넘는 슬롯은 페널티 → 한 번호에 몰리거나 섞이는 현상 방지
"""
import os
import re
import hashlib
import threading
from collections import Counter

import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".embed_cache")
CLIP_MODEL = "openai/clip-vit-large-patch14"

# 가중치는 실데이터 2세트(1장씩 51장 / 2장씩 98장)에서 둘 다 100%가 나오는 구간의 가운데 값
TEXT_WEIGHT = 0.4        # 파일명 캡션 점수 가중치
CHAR_WEIGHT = 0.5        # 인물 옷차림 점수 가중치 (비슷한 장면에 다른 인물인 경우 구분)
EXTRA_SLOT_PENALTY = 2.0 # 번호당 기대 장수보다 1장 더 배정할 때 페널티 (그 이상은 배로 증가)
BOILERPLATE_RATIO = 0.3  # 전체 프롬프트의 30% 이상에 반복되는 구절은 공통 문구(화풍/인물 설명)로 보고 제거
CONFIDENT_MARGIN = 0.3   # 배정 점수와 차순위 점수 차이(z)가 이보다 작으면 '확인 필요'

VALID_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# 윈도우에서 HF 캐시 심볼릭 링크 경고 숨김 (동작에는 영향 없음)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_model_lock = threading.Lock()
_model = None
_processor = None


# ---------------------------------------------------------------- TXT 파싱

def parse_txt_prompts(text_content: str) -> list:
    """TXT 내용을 번호별 항목으로 파싱: [{number, prompt}]"""
    items = []
    line_pattern = re.compile(r'^\s*(?:#|scene|장면|컷)?\s*(\d{1,4})[\.\)\:\-\]\s]+(.*)$', re.IGNORECASE)
    current_num, current_lines = None, []

    def flush():
        if current_num is not None:
            items.append({"number": current_num, "prompt": "\n".join(current_lines).strip()})

    for line in text_content.splitlines():
        m = line_pattern.match(line)
        if m:
            flush()
            current_num = int(m.group(1))
            current_lines = [m.group(2).strip()]
        elif current_num is not None and line.strip():
            current_lines.append(line.strip())
    flush()

    # 번호 형식이 없으면 문단 단위
    if not items:
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text_content) if p.strip()]
        items = [{"number": i, "prompt": p} for i, p in enumerate(paragraphs, start=1)]

    items.sort(key=lambda x: x["number"])
    return items


def _clauses(text: str) -> list:
    return [c.strip() for c in re.split(r'[,.;]\s+|\.$', text) if c.strip()]


def extract_scene_texts(prompts: list) -> list:
    """프롬프트마다 장면 고유 부분만 남김 (인물 설명·화풍 등 반복 문구 제거)"""
    texts = []
    for p in prompts:
        t = p.replace("\n", " ")
        if "—" in t:  # "@인물 설명 — 장면 설명" 형식
            t = t.split("—", 1)[1]
        texts.append(t.lstrip("@ ").strip())

    counts = Counter(c for t in texts for c in {c.lower() for c in _clauses(t)})
    limit = max(2, int(len(texts) * BOILERPLATE_RATIO))
    scenes = []
    for t in texts:
        kept = [c for c in _clauses(t) if counts[c.lower()] < limit]
        scenes.append(", ".join(kept) if kept else t)
    return scenes


def extract_characters(prompts: list) -> list:
    """"@이름, 외모 설명, @이름2, 설명2 — 장면" 형식에서 프롬프트별 {이름: 외모 설명}"""
    result = []
    for p in prompts:
        chars = {}
        if "—" in p:
            for seg in re.split(r',\s*(?=@)', p.split("—", 1)[0].strip()):
                m = re.match(r'@(\w+)\s*,?\s*(.*)', seg.strip(), re.S)
                if m and m.group(2).strip(" ,"):
                    chars[m.group(1)] = m.group(2).strip(" ,")
        result.append(chars)
    return result


# ---------------------------------------------------------------- 파일명 캡션

def filename_caption(filename: str) -> str:
    """Flow 등이 붙인 파일명에서 캡션만 추출: Man_looking_at_wife_20260917133201_2.jpeg → man looking at wife"""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'_\d{10,}(_\d+)?$', '', name)
    name = re.sub(r'_\d+$', '', name)
    return name.replace("_", " ").replace("…", " ").strip()


def leading_number(filename: str):
    """이미 정렬된 파일명(01.png, 01_scene.png, 01_2_scene.png)의 번호"""
    m = re.match(r'^(\d{1,4})(?:_\d+)?(?:_scene)?$', os.path.splitext(filename)[0])
    return int(m.group(1)) if m else None


def _stem(word: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def _analyzer(text: str) -> list:
    return [_stem(w) for w in re.findall(r'[a-z가-힣]{2,}', text.lower())]


def caption_similarity(captions: list, scenes: list) -> np.ndarray:
    vec = TfidfVectorizer(analyzer=_analyzer, sublinear_tf=True)
    try:
        vec.fit(scenes)
        return cosine_similarity(vec.transform(captions), vec.transform(scenes))
    except ValueError:  # 어휘가 비어있음
        return np.zeros((len(captions), len(scenes)))


# ---------------------------------------------------------------- CLIP

def load_model():
    global _model, _processor
    with _model_lock:
        if _model is None:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            torch.set_grad_enabled(False)
            _model = CLIPModel.from_pretrained(CLIP_MODEL).eval()
            _processor = CLIPProcessor.from_pretrained(CLIP_MODEL)
    return _model, _processor


def _file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_embeddings(paths: list, progress=None) -> np.ndarray:
    """이미지 임베딩 (파일 내용 해시로 디스크 캐시 → 이름을 바꿔도 재계산 안 함)"""
    import torch
    os.makedirs(CACHE_DIR, exist_ok=True)
    model, proc = load_model()
    tag = CLIP_MODEL.split("/")[-1]
    out = []
    for i, p in enumerate(paths):
        cache = os.path.join(CACHE_DIR, f"{tag}_{_file_hash(p)}.npy")
        if os.path.exists(cache):
            e = np.load(cache)
        else:
            with Image.open(p) as img:
                x = proc(images=img.convert("RGB"), return_tensors="pt")
            with _model_lock, torch.no_grad():
                e = model.get_image_features(**x)[0].numpy()
            e = e / np.linalg.norm(e)
            np.save(cache, e)
        out.append(e)
        if progress:
            progress(i + 1, len(paths))
    return np.stack(out)


def text_embeddings(texts: list) -> np.ndarray:
    import torch
    model, proc = load_model()
    x = proc(text=texts, return_tensors="pt", padding=True, truncation=True, max_length=77)
    with _model_lock, torch.no_grad():
        e = model.get_text_features(**x).numpy()
    return e / np.linalg.norm(e, axis=1, keepdims=True)


# ---------------------------------------------------------------- 매칭

def _znorm(S: np.ndarray) -> np.ndarray:
    """행/열 방향 표준화 평균 — 특정 프롬프트가 모든 이미지를 끌어당기는 현상 억제"""
    def z(A, axis):
        std = A.std(axis=axis, keepdims=True)
        return np.where(std > 1e-9, (A - A.mean(axis=axis, keepdims=True)) / np.where(std > 1e-9, std, 1), 0)
    return (z(S, 0) + z(S, 1)) / 2


def character_scores(img_e: np.ndarray, prompt_chars: list):
    """이미지마다 각 프롬프트 등장인물의 외모와 얼마나 닮았는지 (인물 정보가 없으면 None)"""
    descs = {}
    for chars in prompt_chars:
        descs.update(chars)
    if not descs:
        return None
    names = list(descs)
    sim = img_e @ text_embeddings([descs[n] for n in names]).T
    std = sim.std(axis=0)
    Z = (sim - sim.mean(axis=0)) / np.where(std > 1e-9, std, 1)  # 인물별로 이미지 간 표준화
    S = np.zeros((img_e.shape[0], len(prompt_chars)))
    for j, chars in enumerate(prompt_chars):
        if chars:
            S[:, j] = Z[:, [names.index(n) for n in chars]].mean(axis=1)
    return S


def assign_with_slots(S: np.ndarray) -> np.ndarray:
    """
    번호마다 기대 장수(이미지 수 // 프롬프트 수, 최소 1)만큼은 페널티 없이,
    그보다 더 받는 슬롯엔 페널티를 줘서 헝가리안 배정. 반환: 이미지별 프롬프트 인덱스
    """
    n_img, n_prompt = S.shape
    base = max(1, n_img // n_prompt)
    n_slots = max(base + 2, -(-n_img // n_prompt) + 1)
    cost = np.concatenate([
        -S + (0 if s < base else EXTRA_SLOT_PENALTY * 2 ** (s - base))
        for s in range(n_slots)
    ], axis=1)
    rows, cols = linear_sum_assignment(cost)
    out = np.zeros(n_img, dtype=int)
    out[rows] = cols % n_prompt
    return out


def match(folder_path: str, prompts: list, progress=None) -> dict:
    """
    반환: {
      "assignments": {filename: {"number", "confident", "candidates": [번호 상위 3개]}},
      "unassigned": [filename]
    }
    """
    files = sorted(f for f in os.listdir(folder_path) if f.lower().endswith(VALID_EXTS))
    numbers = [p["number"] for p in prompts]
    texts = [p["prompt"] for p in prompts]
    scenes = extract_scene_texts(texts)

    img_e = image_embeddings([os.path.join(folder_path, f) for f in files], progress)
    txt_e = text_embeddings(scenes)
    S = _znorm(img_e @ txt_e.T) + TEXT_WEIGHT * _znorm(caption_similarity([filename_caption(f) for f in files], scenes))
    char_S = character_scores(img_e, extract_characters(texts))
    if char_S is not None:
        S += CHAR_WEIGHT * _znorm(char_S)

    # 이미 번호가 붙은 파일은 그 번호에 강하게 고정
    num_idx = {n: j for j, n in enumerate(numbers)}
    for i, f in enumerate(files):
        n = leading_number(f)
        if n in num_idx:
            S[i, num_idx[n]] += 10.0

    assigned = assign_with_slots(S)

    assignments = {}
    for i, f in enumerate(files):
        j = assigned[i]
        order = np.argsort(-S[i])
        best_other = next(k for k in order if k != j) if len(numbers) > 1 else j
        margin = S[i, j] - S[i, best_other]
        assignments[f] = {
            "number": numbers[j],
            "confident": bool(order[0] == j and margin >= CONFIDENT_MARGIN),
            "candidates": [numbers[k] for k in order[:3]],
        }
    return {"assignments": assignments, "unassigned": []}
