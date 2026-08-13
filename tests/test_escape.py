"""사용자 입력이 HTML로 해석되지 않는지 검증한다.

UX 검증 1회차(D6 입력 경계값)에서 발견: 기업명에 넣은 <b>·<img onerror>가
리포트에서 그대로 해석됐다. 기업명은 리포트·관리자·진단자 목록에 모두 나오므로
한 화면만 고치면 다른 화면에서 재발한다.

악의가 없어도 문제다 — 상호에 '&' 나 '<' 가 들어가면 표시가 깨진다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()

EVIL = '<b>굵게</b>&"따옴표"<img src=x onerror=1>'
ATTR = '따옴표" onmouseover="1'

FAKE = {
    "id": "evil1", "type": "self", "company": EVIL,
    "bizNum": "1234567890", "emp": "5~9명", "bizType": "임가공(수주)", "track": "B",
    "gradeLv": 2, "gradeTxt": "LV2. 도입", "totalScore": 13,
    "scores": {"work": 1, "process": 3, "quality": 1, "material": 3, "basic": 1, "leader": 5},
}
FAKE_EXP = {
    "id": "evil2", "type": "expert", "company": EVIL, "expertName": EVIL,
    "bizNum": "1234567890", "emp": "5~9명", "track": "B",
    "gradeLv": 2, "gradeTxt": "LV2. 도입", "totalScore": 14,
    "scores": {"work": 2, "process": 1, "quality": 2, "material": 2, "basic": 3, "leader": 4},
    "causes": {}, "comments": {}, "solutions": {},
    "roadmap": {"short": [], "mid": [], "long": []}, "opinion": EVIL,
}

TAGS = "() => ({b: document.querySelectorAll('%s b').length, " \
       "img: document.querySelectorAll('%s img').length, " \
       "scr: document.querySelectorAll('%s script').length})"


def tag_count(page, sel):
    return page.evaluate(TAGS % (sel, sel, sel))


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 자가진단: 폼 · 리포트 =====
    print("\n=== 자가진단 ===")
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE])

    page.fill("#si-comp", EVIL)
    page.fill("#si-ceo", ATTR)
    page.fill("#si-biznum", "123-45-67890")
    page.fill("#si-phone", "010-1111-2222")
    page.click("div.seg-card:has-text('5~9명')")   # 여기서 폼이 다시 그려진다
    page.wait_for_timeout(300)

    r.check("폼 재렌더 후 기업명 보존", page.input_value("#si-comp") == EVIL,
            page.input_value("#si-comp"))
    r.check("폼 재렌더 후 대표자 보존(속성 이스케이프)", page.input_value("#si-ceo") == ATTR,
            page.input_value("#si-ceo"))
    r.check("폼에 주입된 태그 없음",
            page.evaluate("document.querySelectorAll('#wiz img, #wiz script').length") == 0)

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

    t = tag_count(page, "#rpt-info")
    r.check("리포트 정보표에 주입 없음", t["b"] == 0 and t["img"] == 0 and t["scr"] == 0, str(t))
    r.check("리포트에 기업명이 글자 그대로 표시", EVIL in page.inner_text("#rpt-info"),
            page.inner_text("#rpt-info")[:120])

    # ===== 진단자: 조회 목록 · 완료 목록 · 리포트 =====
    print("\n=== 진단자 ===")
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE, FAKE_EXP])
    page.fill("#expert-name", EVIL)
    page.fill("#pw-input", "2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")
    page.wait_for_function("!document.getElementById('lk-list').innerText.includes('불러오는 중')", timeout=8000)
    page.wait_for_function("!document.getElementById('lk-done').innerText.includes('불러오는 중')", timeout=8000)

    t = tag_count(page, "#lk-list")
    r.check("자가진단 목록에 주입 없음", t["b"] == 0 and t["img"] == 0, str(t))
    t = tag_count(page, "#lk-done")
    r.check("완료 진단 목록에 주입 없음", t["b"] == 0 and t["img"] == 0, str(t))

    # 기업명 검색어도 화면에 되찍힌다
    page.fill("#lk-name", EVIL)
    page.click("#wiz >> text=검색")
    page.wait_for_timeout(600)
    t = tag_count(page, "#lk-result")
    r.check("검색 결과 안내에 주입 없음", t["b"] == 0 and t["img"] == 0, str(t))

    # 임시저장 배너
    page.click("#lk-done >> text=리포트 열기")
    page.wait_for_selector("text=전문가 진단 완료")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1500)
    t = tag_count(page, "#rpt-info")
    r.check("전문가 리포트 정보표에 주입 없음", t["b"] == 0 and t["img"] == 0, str(t))
    r.check("전문가 리포트에 진단자명 글자 그대로", EVIL in page.inner_text("#rpt-info"),
            page.inner_text("#rpt-info")[:140])
    r.check("종합의견에 주입 없음",
            page.evaluate("document.querySelectorAll('#rpt-comment b, #rpt-comment img').length") == 0)

    # ===== 관리자 =====
    print("\n=== 관리자 ===")
    page.goto(f"{BASE}/admin.html")
    page.wait_for_selector("#pw-input")
    page.evaluate("""(docs) => {
        const inst = firebase.firestore();
        inst.collection = () => ({ orderBy: () => ({ get: async () => ({
            docs: docs.map(x => ({ id: x.id, data: () => x })) }) }) });
    }""", [FAKE, FAKE_EXP])
    page.fill("#pw-input", "busan2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("#tbody tr")
    t = tag_count(page, "#tbody")
    r.check("관리자 표에 주입 없음", t["b"] == 0 and t["img"] == 0 and t["scr"] == 0, str(t))
    r.check("관리자 표에 기업명 글자 그대로", EVIL in page.inner_text("#tbody"),
            page.inner_text("#tbody")[:120])

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
