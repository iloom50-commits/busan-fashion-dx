"""영역별 전문가 코멘트와 리포트 영역별 상세 진단을 검증한다.

기존 문제: 진단서인데 영역별 진단 내용이 없었다.
점수만 있고, 그 점수가 무슨 상태인지·왜 그런지·무엇을 도입할지가 흩어져 있었다.
"""
import sys, io, json
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()
CMT = "작업지시서를 사장님이 직접 구두로 전달하고 있어 재작업이 잦다고 함."


def to_first_area(page):
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)
    page.click("text=자가진단 없이 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    page.fill("#ei-comp", "상세검증봉제")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 입력란 =====
    print("\n=== 영역별 전문가 코멘트 입력 ===")
    to_first_area(page)
    r.check("영역 화면에 코멘트 입력란", page.locator("#cmt-work").count() == 1)

    if page.locator("#cmt-work").count() == 1:
        page.fill("#cmt-work", CMT)
        page.wait_for_timeout(300)
        r.check("입력이 state에 저장됨", page.evaluate("state.comments && state.comments.work") == CMT,
                str(page.evaluate("state.comments")))
        r.check("코멘트가 임시저장에 포함",
                CMT in (page.evaluate("localStorage.getItem('dx-expert-draft')") or ""))

        # 점수를 눌러 화면이 다시 그려져도 코멘트가 남아야 한다
        page.click("div:has-text('수기 장부/화이트보드') >> nth=-1")
        page.wait_for_timeout(300)
        r.check("다시 그린 뒤에도 코멘트 유지", page.input_value("#cmt-work") == CMT,
                page.input_value("#cmt-work")[:40])
    else:
        for n in ["입력이 state에 저장됨", "코멘트가 임시저장에 포함", "다시 그린 뒤에도 코멘트 유지"]:
            r.check(n, False, "입력란 없음")

    # ===== 리포트 =====
    print("\n=== 리포트 영역별 상세 진단 ===")
    page.evaluate("""(cmt) => {
        const s = {work:2, process:1, quality:2, material:2, basic:3, leader:4};
        Object.keys(s).forEach(k => state.scores[k] = s[k]);
        state.comments = Object.assign(state.comments || {}, {work: cmt});
        state.causes = {work:['구두 전달 관행 고착','양식 표준화 미비'], quality:['불량 기록 번거로움']};
        state.solutions = {work:['w1'], quality:['q1']};
        state.roadmap = {short:['w1','q1'], mid:[], long:[], _built:true};
        state.opinion = '검증용 종합의견';
        state.step = 'result'; render();
    }""", CMT)
    page.wait_for_selector("text=전문가 진단 완료")

    with page.expect_download() as dl:
        page.click("text=결과 JSON 저장")
    with open(dl.value.path(), encoding="utf-8") as f:
        exported = json.load(f)
    r.check("JSON에 영역별 코멘트 포함", exported.get("comments", {}).get("work") == CMT,
            str(exported.get("comments")))

    saved = page.evaluate("window.__writes[0].data")
    r.check("저장 payload에 코멘트", (saved.get("comments") or {}).get("work") == CMT,
            str(saved.get("comments")))

    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1800)
    body = page.inner_text("#report-dialog")

    r.check("영역별 상세 진단 섹션", page.locator("#rpt-detail").count() == 1)
    detail = page.inner_text("#rpt-detail") if page.locator("#rpt-detail").count() else ""

    r.check("진단 문항 표시", "현장 작업지시서 전달 방식" in detail, detail.replace("\n", " | ")[:160])
    r.check("점수의 척도 문구 표시", "수기 장부/화이트보드" in detail, detail.replace("\n", " | ")[:160])
    r.check("근본 원인 표시", "구두 전달 관행 고착" in detail)
    r.check("전문가 코멘트 표시", CMT in detail)
    r.check("권고 솔루션 표시", "카카오워크·슬랙 공유" in detail)
    r.check("솔루션 예산 표시", "무료~월 1만" in detail)
    r.check("6개 영역 모두 표시",
            all(a in detail for a in ["작업지시", "공정관리", "품질관리", "자재관리", "기초역량", "DX 리더십"]),
            detail.replace("\n", " | ")[:200])
    r.check("DX리더십은 리더십 척도 문구 사용", "적극적 의지" in detail,
            detail.replace("\n", " | ")[-200:])

    print("\n=== 진단 개요 · RFP 상세 ===")
    r.check("진단 개요 섹션", page.locator("#rpt-overview").count() == 1)
    if page.locator("#rpt-overview").count():
        ov = page.inner_text("#rpt-overview")
        r.check("개요에 척도 설명", "5점" in ov and "1점" in ov, ov.replace("\n", " | ")[:160])
    else:
        r.check("개요에 척도 설명", False, "개요 없음")

    rfp = page.inner_text("#rpt-rfp")
    r.check("RFP에 솔루션 설명", "메신저 기반 작업지시 공유" in rfp, rfp.replace("\n", " | ")[:160])
    r.check("RFP에 예산", "무료~월 1만" in rfp, rfp.replace("\n", " | ")[:160])

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
