"""차트 폰트 · 인쇄 여백 · 진단자 정보를 검증한다.

기존 문제:
  · Chart.js 기본 폰트를 그대로 써서 차트의 한글만 다른 폰트로 렌더됐다
  · @page 규칙이 없어 브라우저 인쇄 시 여백이 브라우저 기본값에 좌우됐다
  · 진단자 이름을 입력받는 곳이 아예 없어, 누가 진단했는지 기록이 남지 않았다
"""
import sys, io, json
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()
EXPERT = "나윤정"


def expert_login2(page, name=EXPERT, code="2026"):
    page.fill("#pw-input", code)
    if page.locator("#expert-name").count():
        page.fill("#expert-name", name)
    page.click("#auth-screen >> text=확인")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 차트 폰트 =====
    print("\n=== 차트 폰트 ===")
    for name, url in [("전문가", "expert.html"), ("자가진단", "index.html")]:
        page.goto(f"{BASE}/{url}")
        page.wait_for_function("typeof Chart !== 'undefined'")
        fam = page.evaluate("Chart.defaults.font.family")
        r.check(f"{name} 차트 폰트가 본문과 동일", "Noto Sans KR" in str(fam), str(fam))

    # ===== 인쇄 여백 =====
    print("\n=== 인쇄 여백 ===")
    for name, url in [("전문가", "expert.html"), ("자가진단", "index.html")]:
        page.goto(f"{BASE}/{url}")
        css = page.evaluate("[...document.querySelectorAll('style')].map(s=>s.textContent).join('')")
        r.check(f"{name} @page 여백 규칙", "@page" in css and "margin" in css.split("@page")[1][:120],
                ("@page" + css.split("@page")[1][:60]) if "@page" in css else "없음")

    # ===== 진단자 입력 =====
    print("\n=== 진단자 정보 ===")
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])

    r.check("로그인 화면에 진단자명 입력란", page.locator("#expert-name").count() == 1)

    # 이름 없이 코드만 -> 진입 불가
    page.fill("#pw-input", "2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_timeout(300)
    r.check("진단자명 없이는 진입 불가", page.locator("#auth-screen").is_visible())

    expert_login2(page)
    page.wait_for_selector("text=자가진단 결과 불러오기", timeout=8000)
    r.check("진단자명 입력 후 진입", not page.locator("#auth-screen").is_visible())
    r.check("진단자명이 state에 보관", page.evaluate("state.expertName") == EXPERT,
            str(page.evaluate("state.expertName")))
    r.check("진단자명이 기기에 저장(재입력 불필요)",
            EXPERT in (page.evaluate("localStorage.getItem('dx-expert-name')") or ""))

    # 새로고침 후 자동 채움
    page.reload()
    page.wait_for_function("typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    r.check("새로고침 후 진단자명 자동 채움", page.input_value("#expert-name") == EXPERT,
            page.input_value("#expert-name"))

    # ===== 리포트 표시 =====
    print("\n=== 리포트 표시 ===")
    expert_login2(page)
    page.wait_for_selector("text=자가진단 결과 불러오기")
    page.click("text=자가진단 없이 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    page.fill("#ei-comp", "메타검증봉제")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")
    page.evaluate("""() => {
        const s = {work:2, process:1, quality:2, material:2, basic:3, leader:4};
        Object.keys(s).forEach(k => state.scores[k] = s[k]);
        state.opinion = '검증용'; state.step = 'result'; render();
    }""")
    page.wait_for_selector("text=전문가 진단 완료")

    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    saved = page.evaluate("window.__writes[0].data")
    r.check("저장 payload에 진단자명", saved.get("expertName") == EXPERT, str(saved.get("expertName")))

    with page.expect_download() as dl:
        page.click("text=결과 JSON 저장")
    with open(dl.value.path(), encoding="utf-8") as f:
        exported = json.load(f)
    r.check("JSON에 진단자명", exported.get("expertName") == EXPERT, str(exported.get("expertName")))

    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1500)
    info = page.inner_text("#rpt-info")
    r.check("리포트 정보표에 진단자", EXPERT in info, info.replace("\n", " | ")[:200])
    r.check("리포트 정보표에 진단일", "진단일" in info and "2026" in info,
            info.replace("\n", " | ")[:200])

    # ===== 자가진단 리포트 진단일 =====
    print("\n=== 자가진단 리포트 진단일 ===")
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    page.fill("#si-comp", "메타검증봉제")
    page.fill("#si-ceo", "홍길동")
    page.fill("#si-biznum", "123-45-67890")
    page.fill("#si-phone", "010-1111-2222")
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in [("work",0),("process",1),("quality",0),("material",1),("basic",0),("leader",2)]:
        page.click(f"button[onclick=\"setSelfScore('{aid}',{idx})\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(1200)
    sinfo = page.inner_text("#rpt-info")
    r.check("자가진단 리포트에 진단일", "진단일" in sinfo and "2026" in sinfo,
            sinfo.replace("\n", " | ")[:200])

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
