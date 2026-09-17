// 상태 관리 객체
const state = {
  txtContent: "",
  txtFileName: "",
  folderPath: "",
  scanResult: null,
  currentTab: "all",
  namingFormat: "scene", // scene: 01_scene.png, num_only: 01.png, orig: 01_orig.png
  customNames: {}        // 원본 파일명 -> 사용자가 직접 고친 새 파일명
};

// DOM 요소들
const txtDropzone = document.getElementById("txtDropzone");
const txtFileInput = document.getElementById("txtFileInput");
const txtFileInfo = document.getElementById("txtFileInfo");
const txtFileNameEl = document.getElementById("txtFileName");
const txtParsedCountEl = document.getElementById("txtParsedCount");
const btnRemoveTxt = document.getElementById("btnRemoveTxt");

const folderPathInput = document.getElementById("folderPathInput");
const btnPastePath = document.getElementById("btnPastePath");
const btnScan = document.getElementById("btnScan");
const btnUndo = document.getElementById("btnUndo");
const btnExecuteRename = document.getElementById("btnExecuteRename");

const resultsSection = document.getElementById("resultsSection");
const cardsList = document.getElementById("cardsList");
const unassignedSection = document.getElementById("unassignedSection");
const unassignedGrid = document.getElementById("unassignedGrid");

const loadingOverlay = document.getElementById("loadingOverlay");
const loadingMessage = document.getElementById("loadingMessage");
const toastContainer = document.getElementById("toastContainer");

// 모달
const imageModal = document.getElementById("imageModal");
const modalImg = document.getElementById("modalImg");
const modalCaption = document.getElementById("modalCaption");
const btnCloseModal = document.getElementById("btnCloseModal");

// 1. 이벤트 리스너 등록
document.addEventListener("DOMContentLoaded", () => {
  setupTxtUpload();
  setupFolderInput();
  setupNamingFormat();
  setupFilterTabs();
  setupActions();
  setupModal();
});

// 토스트 메시지 표시
function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// 로딩 토글
function setLoading(show, message = "처리 중...") {
  loadingMessage.textContent = message;
  if (show) {
    loadingOverlay.classList.remove("hidden");
  } else {
    loadingOverlay.classList.add("hidden");
  }
}

// TXT 업로드 핸들러
function setupTxtUpload() {
  txtDropzone.addEventListener("click", () => txtFileInput.click());

  txtDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    txtDropzone.classList.add("drag-over");
  });

  txtDropzone.addEventListener("dragleave", () => {
    txtDropzone.classList.remove("drag-over");
  });

  txtDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    txtDropzone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) {
      handleTxtFile(e.dataTransfer.files[0]);
    }
  });

  txtFileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleTxtFile(e.target.files[0]);
    }
  });

  btnRemoveTxt.addEventListener("click", (e) => {
    e.stopPropagation();
    state.txtContent = "";
    state.txtFileName = "";
    txtFileInput.value = "";
    txtDropzone.classList.remove("hidden");
    txtFileInfo.classList.add("hidden");
  });

  // TXT 경로 직접 입력 불러오기
  const txtDirectPathInput = document.getElementById("txtDirectPathInput");
  const btnLoadDirectTxt = document.getElementById("btnLoadDirectTxt");
  if (btnLoadDirectTxt && txtDirectPathInput) {
    btnLoadDirectTxt.addEventListener("click", async () => {
      const pathVal = txtDirectPathInput.value.trim().replace(/^["']|["']$/g, '');
      if (!pathVal) {
        showToast("TXT 파일 경로를 입력해 주세요.", "warning");
        return;
      }
      setLoading(true, "TXT 파일 읽는 중...");
      try {
        const res = await fetch("/api/read_txt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_path: pathVal })
        });
        const data = await res.json();
        setLoading(false);
        if (data.error) {
          showToast(data.error, "error");
          return;
        }
        state.txtContent = data.content;
        state.txtFileName = data.filename;
        const matches = state.txtContent.match(/^\s*(?:#|scene|장면|컷)?\s*\d{1,4}[\.\)\:\-\]\s]+/gim);
        const count = matches ? matches.length : state.txtContent.split(/\n\s*\n/).filter(x => x.trim()).length;
        txtFileNameEl.textContent = data.filename;
        txtParsedCountEl.textContent = `${count}개 항목 감지됨`;
        txtDropzone.classList.add("hidden");
        txtFileInfo.classList.remove("hidden");
        showToast(`TXT 파일 로드 완료: ${count}개 항목`, "success");
      } catch (err) {
        setLoading(false);
        showToast("파일 읽기 실패: " + err.message, "error");
      }
    });
  }
}

function handleTxtFile(file) {
  if (!file.name.endsWith(".txt")) {
    showToast("텍스트(.txt) 파일만 업로드할 수 있습니다.", "error");
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    state.txtContent = e.target.result;
    state.txtFileName = file.name;
    
    // 대략적인 항목 수 카운트 (미리보기용)
    const matches = state.txtContent.match(/^\s*(?:#|scene|장면|컷)?\s*\d{1,4}[\.\)\:\-\]\s]+/gim);
    const count = matches ? matches.length : state.txtContent.split(/\n\s*\n/).filter(x => x.trim()).length;

    txtFileNameEl.textContent = file.name;
    txtParsedCountEl.textContent = `${count}개 항목 감지됨`;
    txtDropzone.classList.add("hidden");
    txtFileInfo.classList.remove("hidden");
    showToast(`TXT 파일 로드 완료: ${count}개 항목`, "success");
  };
  reader.readAsText(file, "utf-8");
}

// 폴더 경로 입력 핸들러
function setupFolderInput() {
  btnPastePath.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      folderPathInput.value = text.trim().replace(/^["']|["']$/g, '');
      showToast("클립보드 경로를 붙여넣었습니다.", "success");
    } catch (err) {
      folderPathInput.focus();
      showToast("붙여넣기 권한이 없으므로 직접 Ctrl+V 해주세요.", "warning");
    }
  });
}

// 파일명 서식 옵션 변경
function setupNamingFormat() {
  document.querySelectorAll('input[name="nameFormat"]').forEach(radio => {
    radio.addEventListener("change", (e) => {
      document.querySelectorAll('.radio-chip').forEach(c => c.classList.remove('active'));
      e.target.closest('.radio-chip').classList.add('active');
      state.namingFormat = e.target.value;
      state.customNames = {};
      if (state.scanResult) renderDashboard();
    });
  });
}

// subIdx/count: 같은 번호에 이미지가 여러 장이면 01_1, 01_2 형식
function generateNewFilename(num, origFilename, subIdx = 1, count = 1) {
  const ext = origFilename ? origFilename.substring(origFilename.lastIndexOf('.')) : ".png";
  const numStr = String(num).padStart(2, "0") + (count > 1 ? `_${subIdx}` : "");

  if (state.namingFormat === "num_only") {
    return `${numStr}${ext}`;
  } else if (state.namingFormat === "orig") {
    const rawName = origFilename ? origFilename.substring(0, origFilename.lastIndexOf('.')) : "image";
    return `${numStr}_${rawName}${ext}`;
  }
  return `${numStr}_scene${ext}`;
}

// 서버 응답(프롬프트 목록 + 이미지별 배정)으로 번호별 결과 구성
function buildResults() {
  const { prompts, assignments } = state.scanResult;
  const byNumber = {};
  const unassigned = [];
  Object.keys(assignments).sort().forEach(fn => {
    const n = assignments[fn].number;
    if (n === null || n === undefined) unassigned.push(fn);
    else (byNumber[n] = byNumber[n] || []).push(fn);
  });

  let matched = 0, duplicate = 0, missing = 0, review = 0;
  const results = prompts.map(p => {
    const files = byNumber[p.number] || [];
    const status = files.length === 0 ? "missing" : files.length > 1 ? "duplicate_prompt" : "matched";
    const needsReview = files.some(fn => !assignments[fn].confident && !assignments[fn].manual);
    if (status === "missing") missing++;
    if (status === "matched") matched++;
    if (status === "duplicate_prompt") duplicate++;
    if (needsReview) review++;
    return {
      number: p.number,
      prompt: p.prompt,
      scene: p.scene || p.prompt,
      status,
      needsReview,
      files: files.map((fn, i) => ({
        filename: fn,
        newName: state.customNames[fn] || generateNewFilename(p.number, fn, i + 1, files.length)
      }))
    };
  });

  return { results, unassigned, stats: { total: prompts.length, matched, duplicate, missing, review, unassigned: unassigned.length } };
}

function reassign(filename, number) {
  const a = state.scanResult.assignments[filename];
  a.number = number;
  a.manual = true;
  delete state.customNames[filename];
  renderDashboard();
}

// 필터 탭
function setupFilterTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.currentTab = btn.dataset.tab;
      renderCards();
      renderUnassigned();
    });
  });

  // KPI 카드 클릭 시 해당 필터로 자동 전환
  document.querySelectorAll(".stat-card").forEach(card => {
    card.addEventListener("click", () => {
      const filter = card.dataset.filter;
      const targetBtn = document.querySelector(`.tab-btn[data-tab="${filter}"]`);
      if (targetBtn) targetBtn.click();
    });
  });
}

// 메인 액션들
function setupActions() {
  // 1. 자동 스캔 및 분석
  btnScan.addEventListener("click", async () => {
    const folderPath = folderPathInput.value.trim().replace(/^["']|["']$/g, '');
    if (!state.txtContent) {
      showToast("먼저 프롬프트 TXT 파일을 업로드해 주세요.", "warning");
      return;
    }
    if (!folderPath) {
      showToast("이미지 폴더 경로를 입력해 주세요.", "warning");
      return;
    }

    state.folderPath = folderPath;
    setLoading(true, "이미지 내용 분석 중... (처음엔 모델 로딩으로 1~2분 걸릴 수 있어요)");

    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: folderPath,
          txt_content: state.txtContent
        })
      });

      const data = await res.json();
      setLoading(false);

      if (data.error) {
        showToast(data.error, "error");
        return;
      }

      state.scanResult = data;
      state.customNames = {};
      renderDashboard();
      const { stats } = buildResults();
      showToast(`분석 완료: ${stats.total}개 중 ${stats.total - stats.missing}개 번호에 이미지 배정` + (stats.review ? `, ${stats.review}개 확인 필요` : ""), "success");
    } catch (err) {
      setLoading(false);
      showToast("서버 통신 실패: " + err.message, "error");
    }
  });

  // 2. 파일명 일괄 변경 실행
  btnExecuteRename.addEventListener("click", async () => {
    if (!state.scanResult) return;

    const renamePlan = [];
    buildResults().results.forEach(item => {
      item.files.forEach(f => {
        const finalName = f.newName.trim();
        if (finalName && f.filename !== finalName) {
          renamePlan.push({ number: item.number, old_name: f.filename, new_name: finalName });
        }
      });
    });

    if (renamePlan.length === 0) {
      showToast("변경할 파일이 없습니다.", "warning");
      return;
    }

    const names = renamePlan.map(p => p.new_name.toLowerCase());
    if (new Set(names).size !== names.length) {
      showToast("새 파일명 중에 겹치는 이름이 있습니다. 확인해 주세요.", "error");
      return;
    }

    if (!confirm(`총 ${renamePlan.length}개의 이미지 파일 이름을 일괄 변경하시겠습니까?\n(미분류 이미지는 그대로 둡니다. 되돌리기 가능)`)) {
      return;
    }

    setLoading(true, "파일명 일괄 변경 실행 중...");

    try {
      const res = await fetch("/api/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: state.folderPath,
          rename_plan: renamePlan
        })
      });

      const data = await res.json();
      setLoading(false);

      if (data.error) {
        showToast(data.error, "error");
        return;
      }

      showToast(`성공: 총 ${data.renamed_count}개 파일명 변경 완료!`, "success");
      btnScan.click();
    } catch (err) {
      setLoading(false);
      showToast("변경 실행 오류: " + err.message, "error");
    }
  });

  // 3. 되돌리기 (Undo)
  btnUndo.addEventListener("click", async () => {
    if (!confirm("직전에 변경한 파일명을 원래대로 복원하시겠습니까?")) return;

    setLoading(true, "이전 파일명으로 복구 중...");

    try {
      const res = await fetch("/api/undo", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });

      const data = await res.json();
      setLoading(false);

      if (data.error) {
        showToast(data.error, "warning");
        return;
      }

      showToast(`복구 완료: 총 ${data.reverted_count}개 파일이 원래 이름으로 복원되었습니다!`, "success");
      if (state.folderPath && state.txtContent) {
        btnScan.click();
      }
    } catch (err) {
      setLoading(false);
      showToast("되돌리기 오류: " + err.message, "error");
    }
  });
}

// 대시보드 및 결과 렌더링
function renderDashboard() {
  const { stats } = buildResults();
  resultsSection.classList.remove("hidden");

  // KPI 통계
  document.getElementById("statTotalTxt").textContent = stats.total;
  document.getElementById("statMatched").textContent = stats.matched;
  document.getElementById("statReview").textContent = stats.review;
  document.getElementById("statDuplicate").textContent = stats.duplicate;
  document.getElementById("statMissing").textContent = stats.missing;
  document.getElementById("statUnassigned").textContent = stats.unassigned;

  // 탭 카운트
  document.getElementById("countAll").textContent = stats.total;
  document.getElementById("countReview").textContent = stats.review;
  document.getElementById("countMissing").textContent = stats.missing;
  document.getElementById("countDuplicate").textContent = stats.duplicate;
  document.getElementById("countMatched").textContent = stats.matched;
  document.getElementById("countUnassigned").textContent = stats.unassigned;

  renderCards();
  renderUnassigned();
}

// 번호 선택 드롭다운: AI 추천 상위 3개 → 전체 번호 → 미분류
function buildNumberSelect(filename, currentNumber) {
  const a = state.scanResult.assignments[filename];
  const candidates = a.candidates || [];
  const select = document.createElement("select");
  select.className = "number-select";
  const opt = (value, label) => {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = label;
    return o;
  };
  const numLabel = n => `#${String(n).padStart(2, "0")}`;

  const candGroup = document.createElement("optgroup");
  candGroup.label = "AI 추천";
  candidates.forEach(n => candGroup.appendChild(opt(n, numLabel(n))));
  const allGroup = document.createElement("optgroup");
  allGroup.label = "전체 번호";
  state.scanResult.prompts.forEach(p => {
    if (!candidates.includes(p.number)) allGroup.appendChild(opt(p.number, numLabel(p.number)));
  });
  select.appendChild(candGroup);
  select.appendChild(allGroup);
  select.appendChild(opt("", "미분류로 빼기"));
  select.value = currentNumber === null || currentNumber === undefined ? "" : String(currentNumber);

  select.addEventListener("change", () => reassign(filename, select.value === "" ? null : Number(select.value)));
  return select;
}

function renderCards() {
  cardsList.innerHTML = "";
  if (!state.scanResult) return;

  const { results } = buildResults();
  const filter = state.currentTab;

  results.forEach(item => {
    if (filter === "missing" && item.status !== "missing") return;
    if (filter === "duplicate" && item.status !== "duplicate_prompt") return;
    if (filter === "matched" && item.status !== "matched") return;
    if (filter === "review" && !item.needsReview) return;
    if (filter === "unassigned") return;

    const card = document.createElement("div");
    card.className = `match-item-card status-${item.status === 'duplicate_prompt' ? 'duplicate' : item.status}`;

    // 1. 번호 배지
    const numBadge = document.createElement("div");
    numBadge.className = "item-number-badge";
    numBadge.textContent = `#${String(item.number).padStart(2, "0")}`;

    // 2. 프롬프트 본문 및 상태
    const contentArea = document.createElement("div");
    contentArea.className = "item-prompt-content";

    const count = item.files.length;
    let statusBadgeHtml;
    if (count === 0) {
      statusBadgeHtml = `<span class="status-badge badge-danger">✕ 이미지 누락 (0장)</span>`;
    } else if (count > 1) {
      statusBadgeHtml = `<span class="status-badge badge-warning">⚠️ 같은 번호 ${count}장</span>`;
    } else {
      statusBadgeHtml = `<span class="status-badge badge-success">✓ 1:1 매칭</span>`;
    }
    if (item.needsReview) {
      statusBadgeHtml += ` <span class="status-badge badge-review">👀 확인 필요</span>`;
    }

    contentArea.innerHTML = `
      <div>${statusBadgeHtml}</div>
      <p class="prompt-text" title="클릭하여 전체 프롬프트 보기">${escapeHtml(item.scene)}</p>
    `;
    const promptTextEl = contentArea.querySelector(".prompt-text");
    promptTextEl.addEventListener("click", () => {
      const expanded = promptTextEl.classList.toggle("expanded");
      promptTextEl.textContent = expanded ? item.prompt : item.scene;
    });

    // 3. 이미지별 행: 썸네일 + 번호 변경 + 새 파일명
    const filesArea = document.createElement("div");
    filesArea.className = "file-rows";

    if (count === 0) {
      filesArea.innerHTML = `<div class="file-row"><div class="thumb-wrapper"><div class="thumb-missing">이미지 없음</div></div>
        <span class="file-row-orig">다른 번호나 미분류 이미지의 번호를 바꿔서 이 번호로 옮길 수 있습니다.</span></div>`;
    }

    item.files.forEach(f => {
      const a = state.scanResult.assignments[f.filename];
      const fullFilePath = joinPath(state.folderPath, f.filename);
      const row = document.createElement("div");
      row.className = "file-row" + (!a.confident && !a.manual ? " file-row-review" : "");

      const wrap = document.createElement("div");
      wrap.className = "thumb-wrapper";
      wrap.innerHTML = `<img class="thumb-img" src="/api/thumbnail?path=${encodeURIComponent(fullFilePath)}" alt="" title="클릭하여 확대">`;
      wrap.addEventListener("click", () => openModal(fullFilePath, `#${item.number} - ${f.filename}`));

      const controls = document.createElement("div");
      controls.className = "rename-action-box";
      const topLine = document.createElement("div");
      topLine.className = "file-row-top";
      const label = document.createElement("span");
      label.className = "file-row-label";
      label.textContent = a.manual ? "✋ 직접 지정" : (a.confident ? "번호" : "👀 확인 필요");
      topLine.appendChild(label);
      topLine.appendChild(buildNumberSelect(f.filename, item.number));

      const input = document.createElement("input");
      input.type = "text";
      input.className = "rename-input";
      input.value = f.newName;
      input.addEventListener("input", () => { state.customNames[f.filename] = input.value; });

      const orig = document.createElement("span");
      orig.className = "file-row-orig";
      orig.title = f.filename;
      orig.textContent = `원본: ${f.filename}`;

      controls.appendChild(topLine);
      controls.appendChild(input);
      controls.appendChild(orig);
      row.appendChild(wrap);
      row.appendChild(controls);
      filesArea.appendChild(row);
    });

    card.appendChild(numBadge);
    card.appendChild(contentArea);
    card.appendChild(filesArea);
    cardsList.appendChild(card);
  });
}

// 미분류 이미지 그리드 렌더링 (번호를 골라 배정 가능)
function renderUnassigned() {
  if (!state.scanResult) return;
  const { unassigned } = buildResults();
  unassignedGrid.innerHTML = "";

  const visible = unassigned.length > 0 && (state.currentTab === "all" || state.currentTab === "unassigned");
  unassignedSection.classList.toggle("hidden", !visible);

  unassigned.forEach(filename => {
    const fullPath = joinPath(state.folderPath, filename);
    const card = document.createElement("div");
    card.className = "unassigned-card";
    card.innerHTML = `
      <img class="unassigned-thumb" src="/api/thumbnail?path=${encodeURIComponent(fullPath)}" alt="" title="클릭하여 원본 확대">
      <div class="unassigned-name" title="${escapeHtml(filename)}">${escapeHtml(filename)}</div>
    `;
    card.querySelector("img").addEventListener("click", () => openModal(fullPath, filename));
    card.appendChild(buildNumberSelect(filename, null));
    unassignedGrid.appendChild(card);
  });
}

// 모달 제어
function setupModal() {
  btnCloseModal.addEventListener("click", () => imageModal.classList.add("hidden"));
  imageModal.addEventListener("click", (e) => {
    if (e.target === imageModal) imageModal.classList.add("hidden");
  });
}

function openModal(filePath, caption) {
  modalImg.src = `/api/thumbnail?path=${encodeURIComponent(filePath)}`;
  modalCaption.textContent = caption;
  imageModal.classList.remove("hidden");
}

function joinPath(folder, filename) {
  const sep = folder.includes("\\") || !folder.includes("/") ? "\\" : "/";
  return folder.replace(/[\\/]+$/, "") + sep + filename;
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
