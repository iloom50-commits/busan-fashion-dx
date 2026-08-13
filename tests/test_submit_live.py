"""규칙 게시 후에도 실제 진단 제출이 되는지 검증한다.

규칙의 검증 조건이 앱의 실제 저장 필드와 어긋나면 제출이 막힌다.
이 테스트는 SDK를 직접 부르지 않고 '실제 앱 화면을 조작해' 제출한다.
그래야 앱이 보내는 payload 그대로 검증된다.

[주의] 프로덕션에 문서가 생성된다. 규칙상 삭제가 막히므로
       Firebase 콘솔에서 지워야 한다. 문서 ID를 출력한다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LIVE = "https://dx-diagnostic-tool.vercel.app"
MARK = "[제출검증] 삭제해주세요"

r = Results()
created = []

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 자가진단 제출 =====
    print("\n=== 자가진단 실제 제출 ===")
    page.goto(f"{LIVE}/", wait_until="networkidle")
    page.wait_for_selector("#si-biznum")
    page.fill("#si-comp", MARK)
    page.fill("#si-ceo", "검증")
    page.fill("#si-biznum", "000-00-00002")
    page.fill("#si-phone", "000-0000-0000")
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in [("work", 0), ("process", 1), ("quality", 0),
                     ("material", 1), ("basic", 0), ("leader", 2)]:
        page.click(f"button[onclick=\"setSelfScore('{aid}',{idx})\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")
    page.wait_for_timeout(4000)

    status = page.inner_text("#save-status").strip()
    r.check("자가진단 제출 성공", "전송되었습니다" in status, status or "(응답 없음)")

    # ===== 전문가 진단 제출 =====
    print("\n=== 전문가 진단 실제 제출 ===")
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.evaluate("localStorage.clear()")
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof checkPw === 'function'")
    expert_login(page)
    page.evaluate("""(mark) => {
        state.info = {comp: mark, ceo:'검증', phone:'000-0000-0000',
                      emp:'5~9명', biz:'000-00-00002'};
        state.track = 'B';
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.opinion = '규칙 게시 후 제출 검증';
        state.step = 'result'; render();
    }""", MARK)
    page.wait_for_selector("text=전문가 진단 완료")
    page.wait_for_timeout(4000)

    status2 = page.inner_text("#save-status").strip()
    r.check("전문가 진단 제출 성공", "저장되었습니다" in status2, status2 or "(응답 없음)")

    # ===== 생성된 문서 확인 =====
    docs = page.evaluate("""async (mark) => {
        const s = await firebase.firestore().collection('diagnoses').get();
        return s.docs.map(d => ({id: d.id, company: d.data().company, type: d.data().type,
                                 hasCeo: 'ceo' in d.data(), hasPhone: 'phone' in d.data()}));
    }""", MARK)
    b.close()

mine = [d for d in docs if d["company"] == MARK]
r.check("자가진단 문서 생성 확인", any(d["type"] == "self" for d in mine), str(mine))
r.check("전문가 진단 문서 생성 확인", any(d["type"] == "expert" for d in mine), str(mine))
r.check("생성된 문서에 개인정보 없음",
        all(not d["hasCeo"] and not d["hasPhone"] for d in mine), str(mine))
r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))

print(f"\n전체 문서 {len(docs)}건:")
for d in docs:
    print(f"  {d['id']}  {d['company']}  ({d['type']})")

print("\n[콘솔에서 삭제할 문서]")
for d in docs:
    if d["company"] != "그린섬유":
        print(f"  {d['id']}   {d['company']}")

sys.exit(r.summary())
