"""배포된 사이트에서 전문가 리포트를 끝까지 검증한다.

진단자가 실제로 겪는 경로 그대로 조작한다:
로그인 → 자가진단 불러오기 → Track → 기본정보 → 사진 → 6영역 → 로드맵 → 의견 → 리포트

[주의] Firestore 쓰기는 가로챈다. 프로덕션에 문서를 남기지 않는다.
       (규칙 게시 후에는 삭제가 막혀 정리할 수 없기 때문)
"""
import sys, io, os, base64, tempfile
from playwright.sync_api import sync_playwright
from helpers import expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LIVE = "https://dx-diagnostic-tool.vercel.app"
r = Results()

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
photo = os.path.join(tempfile.gettempdir(), "dx_live_photo.png")
with open(photo, "wb") as f:
    f.write(PNG)

BLOCK_WRITE = """() => {
    const inst = firebase.firestore();
    const orig = inst.collection.bind(inst);
    window.__writes = [];
    inst.collection = (name) => {
        const ref = orig(name);
        return new Proxy(ref, { get(t, p) {
            if (p === 'add') return async (d) => { window.__writes.push(d); return {id:'blocked'}; };
            const v = t[p];
            return typeof v === 'function' ? v.bind(t) : v;
        }});
    };
    window.__printed = 0;
    // 인쇄가 호출되는 '그 시점'의 상태를 기록한다.
    // savePDF()는 인쇄 직후 캔버스를 원복하므로, 나중에 보면 이미 사라져 있다.
    window.print = () => {
        window.__printed++;
        window.__imgsAtPrint = ['rpt-radar','rpt-bar'].map(id => {
            const c = document.getElementById(id);
            return { imgs: c.parentNode.querySelectorAll('img').length,
                     canvasHidden: c.style.display === 'none' };
        });
    };
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.evaluate("localStorage.clear()")
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(BLOCK_WRITE)

    print("\n=== 진단자 전체 경로 ===")
    expert_login(page)
    r.check("로그인", page.locator("text=자가진단 결과 불러오기").count() == 1)

    page.wait_for_function(
        "!document.getElementById('lk-list').innerText.includes('불러오는 중')", timeout=25000)
    r.check("실제 자가진단 목록 조회", "실패" not in page.inner_text("#lk-list"),
            page.inner_text("#lk-list").replace("\n", " | ")[:100])

    page.click("text=자가진단 없이 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    page.fill("#ei-comp", "라이브검증봉제")
    page.fill("#ei-ceo", "김대표")
    page.fill("#ei-biz", "111-11-11111")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    page.set_input_files("#f1", photo)
    page.set_input_files("#f2", photo)
    page.wait_for_timeout(800)
    r.check("사진 업로드 후 state 보관", page.evaluate("Object.keys(state.photos).length") == 2,
            str(page.evaluate("Object.keys(state.photos)")))

    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")
    page.evaluate("""() => {
        state.selfScores = {work:1, process:3, quality:1, material:3, basic:1, leader:5};
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.causes = {work:['구두 전달 관행 고착'], quality:['불량 기록 번거로움']};
        state.solutions = {work:['w1'], quality:['q1']};
        state.roadmap = {short:['w1','q1'], mid:[], long:[], _built:true};
        state.opinion = '라이브 검증용 종합의견';
        state.step = 'result'; render();
    }""")
    page.wait_for_selector("text=전문가 진단 완료")
    r.check("결과 화면 도달", True)

    print("\n=== 리포트 ===")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(2000)

    r.check("리포트 다이얼로그 열림", page.evaluate("document.getElementById('report-dialog').open") is True)

    cv = page.evaluate("""() => ['rpt-radar','rpt-bar'].map(id => {
        const c = document.getElementById(id);
        if (!c || !c.width) return {id, w:0, nonblank:0};
        const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let nb = 0; for (let i=3;i<d.length;i+=4) if (d[i] !== 0) nb++;
        return {id, w:c.width, h:c.height, nonblank:nb};
    })""")
    for c in cv:
        r.check(f"{c['id']} 정상 렌더링", c["w"] > 0 and c["nonblank"] > 100, str(c))

    body = page.inner_text("#report-dialog")
    r.check("자가진단 비교표", page.locator("#rpt-compare").count() == 1)
    r.check("근본원인 분석", "구두 전달 관행 고착" in body)
    r.check("현장 사진 2장", page.eval_on_selector_all("#rpt-photos img", "e => e.length") == 2)
    r.check("전문가 의견", "라이브 검증용 종합의견" in body)

    print("\n=== PDF 저장 (인쇄 호출 가로챔) ===")
    page.click("#report-dialog >> text=PDF로 저장")
    page.wait_for_timeout(1200)
    r.check("인쇄 호출됨", page.evaluate("window.__printed") == 1,
            str(page.evaluate("window.__printed")))
    at_print = page.evaluate("window.__imgsAtPrint")
    r.check("인쇄 시점에 차트가 이미지로 변환됨",
            bool(at_print) and all(c["imgs"] == 1 and c["canvasHidden"] for c in at_print),
            str(at_print))

    restored = page.evaluate("""() => ['rpt-radar','rpt-bar'].map(id => {
        const c = document.getElementById(id);
        return { imgs: c.parentNode.querySelectorAll('img').length, display: c.style.display };
    })""")
    r.check("인쇄 후 캔버스 원복", all(c["imgs"] == 0 and c["display"] != 'none' for c in restored),
            str(restored))

    r.check("프로덕션에 문서 미생성", page.evaluate("window.__writes.length") == 1,
            f"가로챈 쓰기 {page.evaluate('window.__writes.length')}건 (실제 저장 아님)")
    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))

    b.close()

sys.exit(r.summary())
