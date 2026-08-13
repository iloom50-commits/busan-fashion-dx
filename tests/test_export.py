"""전문가 진단 결과 JSON 내보내기를 검증한다.

Firestore에 개인정보를 저장하지 않으므로, 담당자가 보관할 사본은 이 파일로 남는다.
따라서 파일에는 대표자·연락처가 들어 있어야 한다.
"""
import sys, io, json
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page.on("dialog", lambda d: d.accept())

    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)

    page.evaluate("""() => {
        state.info = {comp:'테스트봉제', ceo:'홍길동', phone:'010-1111-2222',
                      emp:'5~9명', biz:'123-45-67890'};
        state.track = 'B';
        state.selfRef = 'selfdoc1';
        state.selfScores = {work:1, process:3, quality:1, material:3, basic:1, leader:5};
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.causes.work = ['구두 전달 관행 고착'];
        state.solutions.work = ['w2'];
        state.roadmap = {short:['w2'], mid:[], long:[], _built:true};
        state.opinion = '검증용 종합의견';
        state.step = 'result'; render();
    }""")
    page.wait_for_selector("text=전문가 진단 완료")

    r.check("JSON 저장 버튼 존재", page.locator("text=결과 JSON 저장").count() == 1)

    if page.locator("text=결과 JSON 저장").count() != 1:
        for n in ["파일명에 기업명 포함", "JSON에 대표자 포함", "JSON에 연락처 포함",
                  "JSON에 점수 포함", "JSON에 종합의견 포함", "JSON에 근본원인 포함",
                  "JSON에 로드맵 포함", "JSON에 자가진단 연계 포함"]:
            r.check(n, False, "버튼 없어 진행 불가")
    else:
        with page.expect_download(timeout=10000) as dl:
            page.click("text=결과 JSON 저장")
        download = dl.value
        with open(download.path(), encoding="utf-8") as f:
            data = json.load(f)

        r.check("파일명에 기업명 포함", "테스트봉제" in download.suggested_filename,
                download.suggested_filename)
        r.check("JSON에 대표자 포함", data["info"].get("ceo") == "홍길동", str(data.get("info")))
        r.check("JSON에 연락처 포함", data["info"].get("phone") == "010-1111-2222", str(data.get("info")))
        r.check("JSON에 점수 포함", data["scores"].get("work") == 2, str(data.get("scores")))
        r.check("JSON에 종합의견 포함", data.get("opinion") == "검증용 종합의견", str(data.get("opinion")))
        r.check("JSON에 근본원인 포함", data["causes"].get("work") == ['구두 전달 관행 고착'],
                str(data.get("causes")))
        r.check("JSON에 로드맵 포함", data["roadmap"].get("short") == ['w2'], str(data.get("roadmap")))
        r.check("JSON에 자가진단 연계 포함", data.get("selfRef") == "selfdoc1", str(data.get("selfRef")))

    r.check("리포트 발행 버튼 유지", page.locator("text=전문가 진단 리포트 발행").count() == 1)

    b.close()

sys.exit(r.summary())
