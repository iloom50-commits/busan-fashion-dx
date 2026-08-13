# 개인정보 최소화 + 로컬 임시저장 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Firestore에 개인정보를 저장하지 않도록 바꾸고, 전문가 진단 작성 중 데이터가 유실되지 않게 한다.

**Architecture:** 백엔드를 만들지 않는다. 입력 폼과 PDF 리포트는 그대로 두고 Firestore로 보내는 필드에서만 대표자·연락처·이메일을 제외한다. 작성 중 상태는 `localStorage`에 저장해 네트워크와 무관하게 복원한다. 설계 근거는 [2026-08-13-privacy-minimization-design.md](../specs/2026-08-13-privacy-minimization-design.md)에 있다.

**Tech Stack:** 정적 HTML + Tailwind CDN + Chart.js + Firebase Firestore(compat SDK). 검증은 Python Playwright.

---

## 검증 환경

모든 테스트는 로컬 정적 서버와 Playwright로 실행한다. 프로덕션 Firestore를 오염시키지
않도록 `collection().add()`를 가로채 payload만 수집한다.

**서버 기동:**
```bash
python -m http.server 8899 --directory "c:/Users/osung/.gemini/antigravity/scratch/busan-fashion-dx/v2"
```

**테스트 파일 위치:** `tests/` (저장소 루트)

**공통 헬퍼** — `tests/conftest.py`로 만들어 모든 테스트가 재사용한다.

```python
import json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8899"

# Firestore 쓰기를 가로채 payload만 수집한다 (프로덕션 오염 방지)
PATCH = """(fakes) => {
    const inst = firebase.firestore();
    window.__writes = [];
    inst.collection = (name) => ({
        add: async (data) => { window.__writes.push({collection:name, data}); return {id:'faked'}; },
        where: () => ({ get: async () => ({ docs: fakes.map(f => ({ id: f.id, data: () => f })) }) }),
        orderBy: () => ({ get: async () => ({ docs: [] }) })
    });
}"""

FAKE_SELF = {
    "id": "selfdoc1", "type": "self", "company": "테스트봉제",
    "bizNum": "1234567890", "emp": "5~9명", "bizType": "임가공(수주)", "track": "B",
    "gradeLv": 2, "gradeTxt": "LV2. 도입", "totalScore": 13,
    "scores": {"work": 1, "process": 3, "quality": 1, "material": 3, "basic": 1, "leader": 5},
}

def expert_login(page, code="2026"):
    """진단자 로그인 게이트를 통과한다."""
    page.fill("#pw-input", code)
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")

def fill_self_form(page, comp="테스트봉제", ceo="홍길동", biz="123-45-67890", phone="010-1111-2222"):
    """자가진단 기업정보 화면을 채우고 다음으로 넘어간다."""
    page.fill("#si-comp", comp)
    page.fill("#si-ceo", ceo)
    page.fill("#si-biznum", biz)
    page.fill("#si-phone", phone)
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")

def complete_self_diag(page):
    """Track 선택 후 6개 영역을 모두 채우고 결과 화면까지 진행한다."""
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in [("work",0),("process",1),("quality",0),("material",1),("basic",0),("leader",2)]:
        page.click(f"button[onclick=\\"setSelfScore('{aid}',{idx})\\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")
```

---

## Task 1: Firestore 저장에서 개인정보 제외

**Files:**
- Modify: `v2/index.html` (saveDiagnosis, renderSelfInfo)
- Modify: `v2/expert.html` (saveDiagnosis)
- Modify: `v2/admin.html` (테이블 대표자 열)
- Test: `tests/test_no_pii.py`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_no_pii.py`:

```python
import sys, io
from playwright.sync_api import sync_playwright
from conftest import BASE, PATCH, FAKE_SELF, expert_login, fill_self_form, complete_self_diag

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
PII = ["ceo", "phone", "email"]
results = []

def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" -- {detail}" if detail else ""))

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width":1280,"height":1000})
    page.on("dialog", lambda d: d.accept())

    # --- 자가진단: 저장 payload에 개인정보가 없어야 한다 ---
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    fill_self_form(page)
    complete_self_diag(page)
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    data = page.evaluate("window.__writes[0].data")
    for k in PII:
        check(f"자가진단 저장에 {k} 없음", k not in data, f"keys={sorted(data.keys())}")
    check("자가진단 저장에 company 있음", data.get("company") == "테스트봉제")
    check("자가진단 저장에 bizNum 있음", data.get("bizNum") == "1234567890")

    # --- 같은 진단의 PDF 리포트에는 대표자·연락처가 나와야 한다 ---
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(600)
    rpt = page.inner_text("#rpt-info")
    check("리포트에 대표자 표시", "홍길동" in rpt, rpt.replace("\n"," | ")[:120])
    check("리포트에 연락처 표시", "010-1111-2222" in rpt, rpt.replace("\n"," | ")[:120])
    page.evaluate("document.getElementById('report-dialog').close()")

    # --- 자가진단 화면에 미저장 안내가 있어야 한다 ---
    page.evaluate("restart()")
    page.wait_for_selector("#si-comp")
    check("미저장 안내 문구 표시", "저장되지 않습니다" in page.inner_text("#wiz"))

    # --- 전문가 진단: 저장 payload에 개인정보가 없어야 한다 ---
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    page.evaluate("""() => {
        state.info = {comp:'테스트봉제', ceo:'홍길동', phone:'010-1111-2222', email:'a@b.kr', emp:'5~9명', biz:'123-45-67890'};
        state.track = 'B';
        ['work','process','quality','material','basic','leader'].forEach((a,i)=>state.scores[a]=[2,3,2,4,2,3][i]);
        state.opinion = '검증용'; state.step = 'result'; render();
    }""")
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    ed = page.evaluate("window.__writes[0].data")
    for k in PII:
        check(f"전문가진단 저장에 {k} 없음", k not in ed, f"keys={sorted(ed.keys())}")
    check("전문가진단 저장에 opinion 있음", ed.get("opinion") == "검증용")

    # --- 관리자 대시보드에 대표자 열이 없어야 한다 ---
    page.goto(f"{BASE}/admin.html")
    page.wait_for_selector("#pw-input")
    page.fill("#pw-input", "busan2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("table thead")
    heads = page.eval_on_selector_all("table thead th", "els => els.map(e => e.innerText.trim())")
    check("관리자 테이블에 대표자 열 없음", "대표자" not in heads, str(heads))

    b.close()

fails = [r for r in results if not r[1]]
print(f"\n총 {len(results)}건 중 통과 {len(results)-len(fails)}건, 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인한다**

```bash
python tests/test_no_pii.py
```

기대: `자가진단 저장에 ceo 없음`, `전문가진단 저장에 ceo 없음`, `미저장 안내 문구 표시`,
`관리자 테이블에 대표자 열 없음` 등이 **FAIL**. 리포트 표시 항목은 이미 PASS.

- [ ] **Step 3: `v2/index.html` 저장 필드에서 개인정보를 제외한다**

`saveDiagnosis()` 안의 `db.collection('diagnoses').add({...})`에서 세 줄을 삭제한다.

```javascript
// 삭제할 줄
            ceo: state.info.ceo || '',
            phone: state.info.phone || '',
            email: state.info.email || '',
```

주석을 남겨 의도를 명시한다. `type: 'self',` 바로 위에 추가:

```javascript
        // 대표자·연락처·이메일은 저장하지 않는다 (개인정보 최소화 — specs/2026-08-13 참조)
        await db.collection('diagnoses').add({
```

- [ ] **Step 4: `v2/index.html` 입력 화면에 미저장 안내를 추가한다**

`renderSelfInfo()`의 이메일 입력 `<div>` 바로 뒤에 넣는다.

```javascript
        <p class="text-xs text-gray-400 -mt-3">대표자명·연락처·이메일은 결과보고서 출력에만 사용되며 서버에 저장되지 않습니다.</p>
```

- [ ] **Step 5: `v2/expert.html` 저장 필드에서 개인정보를 제외한다**

`saveDiagnosis()`의 `add({...})`에서 세 줄을 삭제한다.

```javascript
// 삭제할 줄
            ceo: state.info.ceo || '',
            phone: state.info.phone || '',
            email: state.info.email || '',
```

- [ ] **Step 6: `v2/admin.html`에서 대표자 열을 제거한다**

`<thead>`에서 삭제:

```html
                            <th class="text-left">대표자</th>
```

`applyFilter()`의 행 생성 템플릿에서 삭제:

```javascript
            <td>${d.ceo||'-'}</td>
```

`exportCSV()`에도 대표자 열이 있으면 함께 제거한다 (구현 시 해당 함수를 읽고 확인할 것).

- [ ] **Step 7: 테스트를 실행해 통과를 확인한다**

```bash
python tests/test_no_pii.py
```

기대: 전 항목 PASS.

- [ ] **Step 8: 커밋한다**

```bash
git add v2/index.html v2/expert.html v2/admin.html tests/
git commit -m "feat: Firestore 저장에서 대표자·연락처·이메일 제외"
```

---

## Task 2: 전문가 진단 자동 임시저장·복원

**Files:**
- Modify: `v2/expert.html` (임시저장 함수 추가, render/saveDiagnosis/restart, renderLookup 배너)
- Test: `tests/test_draft.py`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_draft.py`:

```python
import sys, io
from playwright.sync_api import sync_playwright
from conftest import BASE, PATCH, FAKE_SELF, expert_login

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
results = []

def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" -- {detail}" if detail else ""))

def enter_diag(page):
    """자가진단을 불러와 첫 영역까지 진입한다."""
    page.fill("#lk-biznum", "123-45-67890")
    page.click("#wiz >> text=조회")
    page.wait_for_selector("text=이 결과로 시작 →")
    page.click("#lk-result >> text=이 결과로 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width":1280,"height":1000})
    page.on("dialog", lambda d: d.accept())

    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    enter_diag(page)

    # 점수와 원인을 입력한다
    page.click("div:has-text('수기 장부/화이트보드') >> nth=-1")
    page.click("div:has-text('구두 전달 관행 고착') >> nth=-1")

    check("작성 중 임시본이 저장됨",
          page.evaluate("!!localStorage.getItem('dx-expert-draft')"))

    # 새로고침 -> 로그인 -> 복원 안내가 떠야 한다
    page.reload()
    page.wait_for_function("typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    check("복원 안내 표시", "작성 중이던 진단이 있습니다" in page.inner_text("#wiz"),
          page.inner_text("#wiz")[:120])
    check("복원 안내에 기업명 표시", "테스트봉제" in page.inner_text("#wiz"))

    # 이어서 작성 -> 입력이 복원돼야 한다
    page.click("text=이어서 작성 →")
    page.wait_for_selector("text=전문가 평가")
    check("점수 복원", page.evaluate("state.scores.work") == 2,
          str(page.evaluate("state.scores")))
    check("근본원인 복원", page.evaluate("(state.causes.work||[]).length") == 1,
          str(page.evaluate("state.causes")))
    check("Track 복원", page.evaluate("state.track") == "B")

    # 새로 시작 -> 임시본이 지워져야 한다
    page.reload()
    page.wait_for_function("typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    page.click("text=새로 시작")
    page.wait_for_timeout(200)
    check("새로 시작 시 임시본 삭제",
          page.evaluate("!localStorage.getItem('dx-expert-draft')"))
    check("새로 시작 후 안내 사라짐", "작성 중이던 진단이 있습니다" not in page.inner_text("#wiz"))

    # 완료 저장 후 -> 임시본이 지워져야 한다
    enter_diag(page)
    page.evaluate("""() => {
        ['work','process','quality','material','basic','leader'].forEach((a,i)=>state.scores[a]=[2,3,2,4,2,3][i]);
        state.opinion='검증용'; state.step='result'; render();
    }""")
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    page.wait_for_timeout(300)
    check("완료 저장 후 임시본 삭제",
          page.evaluate("!localStorage.getItem('dx-expert-draft')"))

    b.close()

fails = [r for r in results if not r[1]]
print(f"\n총 {len(results)}건 중 통과 {len(results)-len(fails)}건, 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인한다**

```bash
python tests/test_draft.py
```

기대: `작성 중 임시본이 저장됨`부터 **FAIL** (localStorage에 아무것도 없음).

- [ ] **Step 3: 임시저장 함수를 추가한다**

`v2/expert.html`의 `let charts = {};` 바로 아래에 넣는다.

```javascript
// ===== 작성 중 임시저장 (브라우저 로컬) =====
// 현장에서 새로고침·배터리 방전으로 30분치 입력이 사라지는 것을 막는다.
// 네트워크와 무관하게 동작한다. 현장 사진은 state에 담기지 않으므로 복원 대상이 아니다.
const DRAFT_KEY = 'dx-expert-draft';

function saveDraft() {
    if (state.step === 'lookup' || state.saved) return;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(state)); } catch(e) {}
}
function loadDraft() {
    try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch(e) { return null; }
}
function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch(e) {}
}

function resumeDraft() {
    const d = loadDraft();
    if (!d) return;
    state = d;
    if (state.info && state.info.comp) {
        document.getElementById('hd-company').innerText = state.info.comp;
        document.getElementById('hd-company').classList.remove('hidden');
    }
    if (state.track) {
        document.getElementById('hd-track').innerText = `Track ${state.track}`;
        document.getElementById('hd-track').classList.remove('hidden');
    }
    render();
}

function discardDraft() { clearDraft(); render(); }

function draftBanner() {
    const d = loadDraft();
    if (!d || !d.info || !d.info.comp) return '';
    const idx = STEPS.findIndex(s => s.s === d.step) + 1;
    return `
    <div class="mx-8 mt-5 border-2 border-amber-300 bg-amber-50 rounded-lg p-4 flex items-center gap-3">
        <span class="text-2xl">📝</span>
        <div class="flex-1 min-w-0">
            <p class="font-bold text-amber-900 text-sm">작성 중이던 진단이 있습니다</p>
            <p class="text-xs text-amber-700 mt-0.5">${d.info.comp} · ${idx}/${STEPS.length}단계</p>
        </div>
        <button onclick="resumeDraft()" class="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg font-bold text-xs whitespace-nowrap">이어서 작성 →</button>
        <button onclick="discardDraft()" class="text-xs text-gray-400 underline whitespace-nowrap">새로 시작</button>
    </div>`;
}
```

- [ ] **Step 4: `render()` 끝에서 임시저장을 호출한다**

`render()` 함수의 마지막 분기 뒤에 한 줄을 추가한다.

```javascript
    else if (state.step === 'result')             renderResult(el);
    saveDraft();
}
```

- [ ] **Step 5: 조회 화면에 복원 배너를 넣는다**

`renderLookup()`의 `el.innerHTML = \`` 시작 직후, `<div class="q-header">` 앞에 배너를 붙인다.

```javascript
function renderLookup(el) {
    el.innerHTML = `
    ${draftBanner()}
    <div class="q-header">
```

- [ ] **Step 6: 완료 저장과 초기화 시 임시본을 지운다**

`saveDiagnosis()`의 성공 분기에 추가한다.

```javascript
        if (statusEl) statusEl.innerHTML = '<span class="text-green-600 text-xs font-bold">✓ 진단 결과가 저장되었습니다</span>';
        clearDraft();
```

`restart()`의 `selfCache = null;` 아래에 추가한다.

```javascript
    clearDraft();
```

- [ ] **Step 7: 테스트를 실행해 통과를 확인한다**

```bash
python tests/test_draft.py
```

기대: 전 항목 PASS.

- [ ] **Step 8: 회귀 확인 — 기존 테스트를 함께 돌린다**

```bash
python tests/test_no_pii.py
```

기대: 전 항목 PASS (Task 1이 깨지지 않았는지 확인).

- [ ] **Step 9: 커밋한다**

```bash
git add v2/expert.html tests/
git commit -m "feat: 전문가 진단 자동 임시저장·이어서 작성"
```

---

## Task 3: 전문가 진단 결과 JSON 내보내기

**Files:**
- Modify: `v2/expert.html` (renderResult, exportExpertResult 추가)
- Test: `tests/test_export.py`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_export.py`:

```python
import sys, io, json
from playwright.sync_api import sync_playwright
from conftest import BASE, PATCH, FAKE_SELF, expert_login

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
results = []

def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" -- {detail}" if detail else ""))

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width":1280,"height":1000}, accept_downloads=True)
    page.on("dialog", lambda d: d.accept())

    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    page.evaluate("""() => {
        state.info = {comp:'테스트봉제', ceo:'홍길동', phone:'010-1111-2222', emp:'5~9명', biz:'123-45-67890'};
        state.track = 'B'; state.selfRef = 'selfdoc1';
        ['work','process','quality','material','basic','leader'].forEach((a,i)=>state.scores[a]=[2,3,2,4,2,3][i]);
        state.opinion = '검증용 종합의견'; state.step = 'result'; render();
    }""")
    page.wait_for_selector("text=전문가 진단 완료")

    check("JSON 저장 버튼 존재", page.locator("text=결과 JSON 저장").count() == 1)

    with page.expect_download(timeout=8000) as dl:
        page.click("text=결과 JSON 저장")
    path = dl.value.path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    check("파일명에 기업명 포함", "테스트봉제" in dl.value.suggested_filename,
          dl.value.suggested_filename)
    check("JSON에 대표자 포함 (Firestore에 없는 정보)", data["info"].get("ceo") == "홍길동")
    check("JSON에 연락처 포함", data["info"].get("phone") == "010-1111-2222")
    check("JSON에 점수 포함", data["scores"].get("work") == 2, str(data.get("scores")))
    check("JSON에 종합의견 포함", data.get("opinion") == "검증용 종합의견")
    check("JSON에 자가진단 연계 포함", data.get("selfRef") == "selfdoc1")

    b.close()

fails = [r for r in results if not r[1]]
print(f"\n총 {len(results)}건 중 통과 {len(results)-len(fails)}건, 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: 테스트를 실행해 실패를 확인한다**

```bash
python tests/test_export.py
```

기대: `JSON 저장 버튼 존재`부터 **FAIL**.

- [ ] **Step 3: 내보내기 함수를 추가한다**

`v2/expert.html`의 `printExpertReport()` 함수 바로 위에 넣는다.

```javascript
// Firestore에는 개인정보를 저장하지 않으므로, 담당자가 보관할 사본은 이 파일로 남긴다.
function exportExpertResult() {
    const data = JSON.stringify({
        info: state.info,
        track: state.track,
        scores: state.scores,
        causes: state.causes,
        solutions: state.solutions,
        roadmap: { short: state.roadmap.short, mid: state.roadmap.mid, long: state.roadmap.long },
        opinion: state.opinion,
        grade: state.grade,
        selfRef: state.selfRef,
        selfScores: state.selfScores,
        exportedAt: new Date().toISOString()
    }, null, 2);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([data], {type:'application/json'}));
    a.download = `전문가진단_${state.info.comp||'결과'}_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
}
```

- [ ] **Step 4: 결과 화면에 버튼을 추가한다**

`renderResult()`의 리포트 발행 버튼을 두 개짜리 행으로 바꾼다.

기존:
```javascript
        <button onclick="printExpertReport()" class="w-full bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-bold shadow transition-all mb-3">
            📄 전문가 진단 리포트 발행
        </button>
```

변경 후:
```javascript
        <div class="flex gap-3 mb-3">
            <button onclick="exportExpertResult()" class="flex-1 border-2 border-green-600 text-green-700 hover:bg-green-50 py-3 rounded-lg font-bold text-sm transition-all">
                💾 결과 JSON 저장
            </button>
            <button onclick="printExpertReport()" class="flex-1 bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-bold text-sm shadow transition-all">
                📄 전문가 진단 리포트 발행
            </button>
        </div>
```

- [ ] **Step 5: 테스트를 실행해 통과를 확인한다**

```bash
python tests/test_export.py
```

기대: 전 항목 PASS.

- [ ] **Step 6: 회귀 확인**

```bash
python tests/test_no_pii.py
python tests/test_draft.py
```

기대: 둘 다 전 항목 PASS.

- [ ] **Step 7: 커밋한다**

```bash
git add v2/expert.html tests/
git commit -m "feat: 전문가 진단 결과 JSON 내보내기"
```

---

## Task 4: Firestore 보안규칙 갱신

**Files:**
- Modify: `firestore.rules`

이 작업은 파일 수정까지만 자동화한다. **게시는 Firebase 콘솔에서 사용자가 직접 수행한다.**

- [ ] **Step 1: `firestore.rules`의 read 규칙과 주석을 갱신한다**

기존 파일은 Firebase Auth 도입을 전제로 작성돼 있다. 채택된 설계에 맞게 고친다.

`allow read` 부분을 다음으로 교체한다.

```
      // --- 읽기 ---
      // 의도적으로 열어 둔다. 개인정보(대표자·연락처·이메일)를 저장하지 않으므로
      // 노출되는 것은 기업명·사업자번호·진단점수뿐이다. 이를 감수하는 대신
      // 백엔드 없이 진단자 조회와 관리자 대시보드를 유지한다.
      // 근거: docs/superpowers/specs/2026-08-13-privacy-minimization-design.md
      allow read: if true;
```

파일 상단 주석에서 "1단계 / 2단계" 및 Firebase Auth 전환 안내를 삭제하고
다음으로 교체한다.

```
// [채택한 방식] 개인정보 최소화 (백엔드 미도입)
//   대표자·연락처·이메일을 Firestore에 저장하지 않는다. 저장하지 않은 정보는
//   유출되지 않으므로, 읽기를 열어 두어도 개인정보 노출이 발생하지 않는다.
//   대표자·연락처 명부는 부산테크노파크가 별도로 보유한다 (과업지시서 66행).
//
// [이 규칙이 막는 것]
//   · 저장된 진단 기록의 수정·삭제
//   · 형식이 맞지 않는 문서 생성
//   · 클라이언트가 임의 시각을 timestamp로 넣는 것
//
// [이 규칙이 막지 않는 것]
//   · 기업명·사업자번호·진단점수 조회. 이는 위 설계에 따른 의도된 결과다.
```

- [ ] **Step 2: 커밋한다**

```bash
git add firestore.rules
git commit -m "security: 개인정보 최소화 방식에 맞춰 Firestore 규칙 갱신"
```

- [ ] **Step 3: 사용자에게 게시를 요청한다**

Firebase 콘솔 > 프로젝트 `dx-tool-d262e` > Firestore Database > 규칙 탭에
`firestore.rules` 내용을 붙여넣고 게시하도록 안내한다.

- [ ] **Step 4: 게시 후 프로덕션에서 검증한다**

`tests/test_rules_live.py`를 작성해 실행한다.

```python
import sys, io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
LIVE = "https://dx-diagnostic-tool.vercel.app"
KEEP_ID = "Dxk2iWqtUURAlXlVc76A"   # 그린섬유 — 절대 지워지면 안 된다
results = []

def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" -- {detail}" if detail else ""))

with sync_playwright() as pw:
    b = pw.chromium.launch(); page = b.new_page()
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof firebase !== 'undefined'")

    out = page.evaluate("""async (keepId) => {
        const db = firebase.firestore();
        const r = {};
        try { const s = await db.collection('diagnoses').get(); r.read = 'OK:' + s.size; }
        catch(e) { r.read = 'DENIED'; }
        try { await db.collection('diagnoses').doc(keepId).update({company:'해킹시도'}); r.update = 'OK'; }
        catch(e) { r.update = 'DENIED'; }
        try { await db.collection('diagnoses').doc(keepId).delete(); r.delete = 'OK'; }
        catch(e) { r.delete = 'DENIED'; }
        try { await db.collection('diagnoses').add({junk:'x'}); r.badCreate = 'OK'; }
        catch(e) { r.badCreate = 'DENIED'; }
        const snap = await db.collection('diagnoses').doc(keepId).get();
        r.keepAlive = snap.exists ? snap.data().company : '(사라짐)';
        return r;
    }""", KEEP_ID)
    b.close()

check("읽기는 허용됨 (의도된 동작)", out["read"].startswith("OK"), out["read"])
check("수정 차단", out["update"] == "DENIED", out["update"])
check("삭제 차단", out["delete"] == "DENIED", out["delete"])
check("형식 미달 생성 차단", out["badCreate"] == "DENIED", out["badCreate"])
check("그린섬유 기록 보존", out["keepAlive"] == "그린섬유", out["keepAlive"])

fails = [r for r in results if not r[1]]
print(f"\n총 {len(results)}건 중 통과 {len(results)-len(fails)}건, 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
```

```bash
python tests/test_rules_live.py
```

기대: 전 항목 PASS.

- [ ] **Step 5: 게시 후 자가진단 제출이 여전히 되는지 확인한다**

규칙 검증 조건이 실제 저장 필드와 어긋나면 제출이 막힌다. 실제 제출로 확인한다.

`tests/test_submit_live.py`를 작성해 실행하고, **확인 후 생성된 문서를 지운다.**
(규칙 게시 후에는 클라이언트 삭제가 차단되므로 Firebase 콘솔에서 지워야 한다.
따라서 이 테스트로 생성된 문서 ID를 반드시 출력해 사용자에게 알린다.)

- [ ] **Step 6: 배포하고 최종 확인한다**

```bash
git push origin master
```

배포 반영 후 라이브에서 진단자 흐름을 한 번 처음부터 끝까지 확인한다.

---

## Self-Review 결과

**Spec 커버리지**

| 설계 문서 요구사항 | 대응 Task |
|---|---|
| Firestore 저장에서 개인정보 제외 | Task 1 Step 3, 5 |
| 자가진단 화면 안내 문구 | Task 1 Step 4 |
| 관리자 대시보드 대표자 열 제거 | Task 1 Step 6 |
| 자동 임시저장 (render 시점) | Task 2 Step 3, 4 |
| 복원 안내 배너 | Task 2 Step 5 |
| 완료·초기화 시 임시본 삭제 | Task 2 Step 6 |
| 결과 JSON 내보내기 | Task 3 |
| 규칙 갱신 및 게시 | Task 4 |
| 완료 기준 1 (저장에 PII 없음) | test_no_pii.py |
| 완료 기준 2 (PDF에는 표시) | test_no_pii.py |
| 완료 기준 3~4 (복원·삭제) | test_draft.py |
| 완료 기준 5 (수정·삭제 거부) | test_rules_live.py |
| 완료 기준 6 (제출 정상) | Task 4 Step 5 |
| 완료 기준 7 (조회·대시보드 동작) | test_rules_live.py + Task 4 Step 6 |

**남은 위험**

- Task 4 Step 5는 프로덕션에 문서를 1건 생성한다. 규칙 게시 후에는 클라이언트에서
  지울 수 없으므로 Firebase 콘솔에서 삭제해야 한다. 문서 ID를 반드시 출력한다.
- `exportCSV()`의 대표자 열 처리는 해당 함수를 읽고 확인해야 한다 (Task 1 Step 6).
