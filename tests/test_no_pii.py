"""Firestore 저장 payload에 개인정보가 없는지 검증한다.

대표자·연락처·이메일은 화면과 PDF 리포트에는 나오되 서버에는 저장되지 않아야 한다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, fill_self_form, complete_self_diag, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PII = ["ceo", "phone", "email"]
r = Results()

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page.on("dialog", lambda d: d.accept())

    # ===== 자가진단: 저장 payload에 개인정보가 없어야 한다 =====
    print("\n=== 자가진단 저장 ===")
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    fill_self_form(page)
    complete_self_diag(page)
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)

    data = page.evaluate("window.__writes[0].data")
    for k in PII:
        r.check(f"자가진단 저장에 {k} 없음", k not in data, f"keys={sorted(data.keys())}")
    r.check("자가진단 저장에 company 있음", data.get("company") == "테스트봉제", str(data.get("company")))
    r.check("자가진단 저장에 bizNum 있음", data.get("bizNum") == "1234567890", str(data.get("bizNum")))
    r.check("자가진단 저장에 scores 있음", len(data.get("scores") or {}) == 6, str(data.get("scores")))

    # ===== PDF 리포트에는 대표자·연락처가 나와야 한다 =====
    print("\n=== PDF 리포트 표시 ===")
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(600)
    rpt = page.inner_text("#rpt-info")
    r.check("리포트에 대표자 표시", "홍길동" in rpt, rpt.replace("\n", " | ")[:120])
    r.check("리포트에 연락처 표시", "010-1111-2222" in rpt, rpt.replace("\n", " | ")[:120])
    page.evaluate("document.getElementById('report-dialog').close()")

    # ===== 입력 화면에 미저장 안내가 있어야 한다 =====
    print("\n=== 미저장 안내 ===")
    page.evaluate("restart()")
    page.wait_for_selector("#si-comp")
    r.check("미저장 안내 문구 표시", "저장되지 않습니다" in page.inner_text("#wiz"))

    # ===== 전문가 진단: 저장 payload에 개인정보가 없어야 한다 =====
    print("\n=== 전문가 진단 저장 ===")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    page.evaluate("""() => {
        state.info = {comp:'테스트봉제', ceo:'홍길동', phone:'010-1111-2222',
                      email:'a@b.kr', emp:'5~9명', biz:'123-45-67890'};
        state.track = 'B';
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.opinion = '검증용'; state.step = 'result'; render();
    }""")
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)

    ed = page.evaluate("window.__writes[0].data")
    for k in PII:
        r.check(f"전문가진단 저장에 {k} 없음", k not in ed, f"keys={sorted(ed.keys())}")
    r.check("전문가진단 저장에 opinion 있음", ed.get("opinion") == "검증용", str(ed.get("opinion")))
    r.check("전문가진단 저장에 bizNum 있음", ed.get("bizNum") == "1234567890", str(ed.get("bizNum")))

    # ===== 관리자 대시보드에 대표자 열이 없어야 한다 =====
    print("\n=== 관리자 대시보드 ===")
    page.goto(f"{BASE}/admin.html")
    page.wait_for_selector("#pw-input")
    page.fill("#pw-input", "busan2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("table thead", state="attached")
    heads = page.eval_on_selector_all("table thead th", "els => els.map(e => e.innerText.trim())")
    r.check("관리자 테이블에 대표자 열 없음", "대표자" not in heads, str(heads))

    csv_src = page.evaluate("exportCSV.toString()")
    r.check("CSV 헤더에 대표자 없음", "'대표자'" not in csv_src)
    r.check("CSV 행에 d.ceo 없음", "d.ceo" not in csv_src)

    b.close()

sys.exit(r.summary())
