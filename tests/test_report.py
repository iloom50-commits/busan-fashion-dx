"""전문가 진단 리포트를 검증한다.

기존 문제: 숨겨진 영역에서 차트를 그려 캔버스가 0x0이 되고 차트가 깨졌다.
그리고 입력받은 근본원인·자가진단 점수·현장 사진이 리포트에 나오지 않았다.
"""
import sys, io, base64, os, tempfile
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()

# 사진 업로드용 임시 PNG (1x1)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
photo_path = os.path.join(tempfile.gettempdir(), "dx_test_photo.png")
with open(photo_path, "wb") as f:
    f.write(PNG)


def setup(page, with_self=True, with_photo=True):
    """결과 화면 직전까지 상태를 만든다."""
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
    page.fill("#ei-comp", "리포트검증봉제")
    page.fill("#ei-ceo", "김대표")
    page.fill("#ei-biz", "111-11-11111")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    if with_photo:
        page.set_input_files("#f1", photo_path)
        page.set_input_files("#f2", photo_path)
        page.wait_for_timeout(600)
    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")
    page.evaluate("""(withSelf) => {
        if (withSelf) state.selfScores = {work:1, process:3, quality:1, material:3, basic:1, leader:5};
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.causes = {work:['구두 전달 관행 고착','양식 표준화 미비'], quality:['불량 기록 번거로움']};
        state.solutions = {work:['w1','w3'], quality:['q1'], material:['m1']};
        state.roadmap = {short:['w1','q1','m1'], mid:['w3'], long:[], _built:true};
        state.opinion = '현장 전반이 수기 기반이며 작업지시 디지털화가 최우선 과제로 판단됨.';
        state.step = 'result'; render();
    }""", with_self)
    page.wait_for_selector("text=전문가 진단 완료")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 차트가 실제로 그려지는가 =====
    print("\n=== 차트 렌더링 ===")
    setup(page)
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1500)

    dlg = page.evaluate("""() => {
        const d = document.getElementById('report-dialog');
        return d ? d.open : null;
    }""")
    r.check("리포트 다이얼로그 열림", dlg is True, str(dlg))

    cv = page.evaluate("""() => ['rpt-radar','rpt-bar'].map(id => {
        const c = document.getElementById(id);
        if (!c) return {id, exists:false};
        let nb = null;
        if (c.width > 0 && c.height > 0) {
            const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            nb = 0; for (let i=3;i<d.length;i+=4) if (d[i] !== 0) nb++;
        }
        return {id, w:c.width, h:c.height, nonblank:nb};
    })""")
    for c in cv:
        r.check(f"{c['id']} 캔버스 크기 > 0", c.get("w", 0) > 0 and c.get("h", 0) > 0, str(c))
        r.check(f"{c['id']} 실제로 그려짐", (c.get("nonblank") or 0) > 100, str(c))

    r.check("PDF 저장 버튼 존재", page.locator("#report-dialog >> text=PDF로 저장").count() == 1)

    # ===== 새로 들어가야 할 내용 =====
    print("\n=== 리포트 내용 ===")
    body = page.inner_text("#report-dialog") if page.locator("#report-dialog").count() else ""
    r.check("근본원인 분석 표시", "구두 전달 관행 고착" in body and "불량 기록 번거로움" in body,
            body.replace("\n", " | ")[:160])
    r.check("자가진단 비교 섹션 존재", page.locator("#rpt-compare").count() == 1)

    if page.locator("#rpt-compare").count() == 1:
        comp = page.inner_text("#rpt-compare")
        r.check("비교표에 자가 점수 표시", "1" in comp and "5" in comp, comp.replace("\n", " | ")[:160])
        r.check("비교표에 격차 표시", "격차" in comp or "차이" in comp, comp.replace("\n", " | ")[:160])
    else:
        r.check("비교표에 자가 점수 표시", False, "섹션 없음")
        r.check("비교표에 격차 표시", False, "섹션 없음")

    imgs = page.eval_on_selector_all("#rpt-photos img", "els => els.length")
    r.check("현장 사진 2장 표시", imgs == 2, f"img={imgs}")

    r.check("기존 내용 유지 (로드맵)", "이행 로드맵" in body)
    r.check("기존 내용 유지 (RFP)", "맞춤형 기술 수요" in body)
    r.check("기존 내용 유지 (전문가 의견)", "최우선 과제로 판단됨" in body)

    # ===== 자가진단·사진이 없을 때는 해당 섹션이 나오지 않아야 한다 =====
    print("\n=== 자가진단·사진 없을 때 ===")
    setup(page, with_self=False, with_photo=False)
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1200)
    r.check("자가진단 없으면 비교 섹션 미표시", page.locator("#rpt-compare").count() == 0)
    r.check("사진 없으면 사진 섹션 미표시", page.locator("#rpt-photos").count() == 0)
    r.check("이 경우에도 차트는 그려짐",
            page.evaluate("document.getElementById('rpt-radar').width") > 0)

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
