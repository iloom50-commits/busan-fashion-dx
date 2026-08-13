"""전문가 진단 작성 중 임시저장·복원을 검증한다.

현장에서 새로고침·배터리 방전으로 입력이 사라지지 않아야 한다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()


def enter_diag(page):
    """자가진단을 불러와 첫 영역(작업지시)까지 진입한다."""
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


def fresh_login(page):
    """페이지를 새로 열고 로그인까지 진행한다."""
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    expert_login(page)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")

    # ===== 작성 중 임시저장 =====
    print("\n=== 작성 중 임시저장 ===")
    fresh_login(page)
    enter_diag(page)
    # 세 종류의 입력이 모두 임시저장돼야 한다.
    # 이 핸들러들은 render()를 거치지 않고 화면만 다시 그린다.
    page.click("div:has-text('수기 장부/화이트보드') >> nth=-1")      # setScore
    page.click("div:has-text('구두 전달 관행 고착') >> nth=-1")       # toggleCause
    page.click("div.sol-card:has-text('QR코드 작업지시서')")           # toggleSolution

    r.check("작성 중 임시본이 저장됨",
            page.evaluate("!!localStorage.getItem('dx-expert-draft')"))

    # ===== 새로고침 후 복원 안내 =====
    # 배너를 #draft-banner로 특정한다. 아래 자가진단 목록에도 같은 기업명이 있어
    # 화면 전체 텍스트로 검사하면 거짓 통과한다.
    print("\n=== 새로고침 후 복원 안내 ===")
    fresh_login(page)
    has_banner = page.locator("#draft-banner").count() == 1
    r.check("복원 안내 배너 표시", has_banner, page.inner_text("#wiz").replace("\n", " | ")[:120])
    if has_banner:
        banner = page.inner_text("#draft-banner")
        r.check("배너에 안내 문구", "작성 중이던 진단이 있습니다" in banner, banner.replace("\n", " | "))
        r.check("배너에 기업명 표시", "테스트봉제" in banner, banner.replace("\n", " | "))
    else:
        r.check("배너에 안내 문구", False, "배너 없음")
        r.check("배너에 기업명 표시", False, "배너 없음")

    # ===== 이어서 작성 =====
    print("\n=== 이어서 작성 ===")
    if has_banner:
        page.click("#draft-banner >> text=이어서 작성 →")
        page.wait_for_selector("text=전문가 평가")
        r.check("점수 복원", page.evaluate("state.scores.work") == 2, str(page.evaluate("state.scores")))
        r.check("근본원인 복원", page.evaluate("(state.causes.work||[]).length") == 1,
                str(page.evaluate("state.causes")))
        r.check("선택 솔루션 복원", page.evaluate("(state.solutions.work||[]).includes('w2')"),
                str(page.evaluate("state.solutions")))
        r.check("Track 복원", page.evaluate("state.track") == "B", str(page.evaluate("state.track")))
        r.check("기업명 복원", page.evaluate("state.info.comp") == "테스트봉제",
                str(page.evaluate("state.info")))
        r.check("헤더에 기업명 표시", page.inner_text("#hd-company") == "테스트봉제")
    else:
        for n in ["점수 복원", "근본원인 복원", "선택 솔루션 복원", "Track 복원",
                  "기업명 복원", "헤더에 기업명 표시"]:
            r.check(n, False, "배너 없어 진행 불가")

    # ===== 새로 시작 =====
    print("\n=== 새로 시작 ===")
    fresh_login(page)
    if page.locator("#draft-banner").count() == 1:
        page.click("#draft-banner >> text=새로 시작")
        page.wait_for_timeout(300)
    r.check("새로 시작 시 임시본 삭제",
            page.evaluate("!localStorage.getItem('dx-expert-draft')"))
    r.check("새로 시작 후 배너 사라짐", page.locator("#draft-banner").count() == 0)

    # ===== 완료 저장 후 =====
    print("\n=== 완료 저장 후 ===")
    enter_diag(page)
    page.evaluate("""() => {
        ['work','process','quality','material','basic','leader']
            .forEach((a,i) => state.scores[a] = [2,3,2,4,2,3][i]);
        state.opinion = '검증용'; state.step = 'result'; render();
    }""")
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    page.wait_for_timeout(500)
    r.check("완료 저장 후 임시본 삭제",
            page.evaluate("!localStorage.getItem('dx-expert-draft')"))

    fresh_login(page)
    r.check("완료 후 복원 배너 없음", page.locator("#draft-banner").count() == 0)

    b.close()

sys.exit(r.summary())
