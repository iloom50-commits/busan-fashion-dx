"""완료한 전문가 진단을 다시 열어 리포트를 재발행할 수 있는지 검증한다.

기존 문제: 완료 저장에 성공하면 임시본이 지워지고, 저장된 전문가 진단을 다시
불러오는 경로가 없었다. 진단자가 PDF 저장을 잊고 화면을 닫으면 30분치 진단으로
보고서를 만들 수 없었다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()
ME = "나윤정"
OTHER = "김철수"

# 저장돼 있다고 가정하는 전문가 진단 2건 (본인 1 · 타인 1)
MINE = {
    "id": "expdoc1", "type": "expert", "company": "플리에라이트",
    "bizNum": "6078112345", "emp": "5~9명", "track": "B", "expertName": ME,
    "gradeLv": 2, "gradeTxt": "LV2. 도입", "totalScore": 14,
    "scores": {"work": 2, "process": 1, "quality": 2, "material": 2, "basic": 3, "leader": 4},
    "causes": {"work": ["구두 전달 관행 고착"], "quality": ["불량 기록 번거로움"]},
    "comments": {"work": "작업지시서를 대표자가 직접 구두로 전달하고 있음."},
    "solutions": {"work": ["w1"], "quality": ["q1"]},
    "roadmap": {"short": ["w1", "q1"], "mid": [], "long": []},
    "opinion": "봉제 임가공 중심의 수주 구조로 작업지시가 구두에 의존하고 있음.",
    "selfRef": "selfdoc1",
    "selfScores": {"work": 3, "process": 1, "quality": 3, "material": 1, "basic": 3, "leader": 5},
}
THEIRS = {
    "id": "expdoc2", "type": "expert", "company": "다른봉제",
    "bizNum": "1112233333", "emp": "1~4명", "track": "A", "expertName": OTHER,
    "gradeLv": 1, "gradeTxt": "LV1. 기초", "totalScore": 8,
    "scores": {"work": 1, "process": 1, "quality": 1, "material": 1, "basic": 2, "leader": 2},
    "causes": {}, "comments": {}, "solutions": {},
    "roadmap": {"short": [], "mid": [], "long": []}, "opinion": "타 진단자 작성",
}
FAKES = [FAKE_SELF, MINE, THEIRS]


def login(page, name=ME):
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, FAKES)
    page.fill("#expert-name", name)
    page.fill("#pw-input", "2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    print("\n=== 완료 진단 목록 ===")
    login(page)
    page.wait_for_function(
        "document.getElementById('lk-done') && !document.getElementById('lk-done').innerText.includes('불러오는 중')",
        timeout=8000)

    r.check("완료 진단 목록 섹션 존재", page.locator("#lk-done").count() == 1)
    done = page.inner_text("#lk-done") if page.locator("#lk-done").count() else ""
    r.check("내 진단 표시", "플리에라이트" in done, done.replace("\n", " | ")[:160])
    r.check("등급·점수 표시", "LV2. 도입" in done and "14" in done, done.replace("\n", " | ")[:160])
    r.check("진단자 이름 표시", ME in done, done.replace("\n", " | ")[:160])
    r.check("다른 진단자 것도 보임", "다른봉제" in done, done.replace("\n", " | ")[:160])

    order = page.eval_on_selector_all(
        "#lk-done .done-card", "els => els.map(e => e.getAttribute('data-company'))")
    r.check("내 진단이 먼저 표시", order and order[0] == "플리에라이트", str(order))

    # 자가진단 목록에는 전문가 진단이 섞이지 않아야 한다
    lst = page.inner_text("#lk-list")
    r.check("자가진단 목록과 분리", "플리에라이트" not in lst and "테스트봉제" in lst,
            lst.replace("\n", " | ")[:140])

    print("\n=== 다시 열기 ===")
    page.click("#lk-done >> text=리포트 열기")
    page.wait_for_selector("text=전문가 진단 완료", timeout=8000)

    st = page.evaluate("""() => ({
        comp: state.info.comp, track: state.track, saved: state.saved,
        work: state.scores.work, leader: state.scores.leader,
        cause: (state.causes.work||[])[0],
        comment: (state.comments||{}).work,
        sol: (state.solutions.work||[])[0],
        short: (state.roadmap.short||[]).length,
        opinion: state.opinion,
        selfWork: (state.selfScores||{}).work,
        expert: state.expertName
    })""")
    r.check("기업명 복원", st["comp"] == "플리에라이트", str(st))
    r.check("Track 복원", st["track"] == "B", str(st["track"]))
    r.check("점수 복원", st["work"] == 2 and st["leader"] == 4, str(st))
    r.check("근본원인 복원", st["cause"] == "구두 전달 관행 고착", str(st["cause"]))
    r.check("전문가 코멘트 복원", "구두로 전달" in (st["comment"] or ""), str(st["comment"]))
    r.check("선택 솔루션 복원", st["sol"] == "w1", str(st["sol"]))
    r.check("로드맵 복원", st["short"] == 2, str(st["short"]))
    r.check("종합의견 복원", "임가공" in (st["opinion"] or ""), str(st["opinion"])[:60])
    r.check("자가진단 점수 복원", st["selfWork"] == 3, str(st["selfWork"]))
    r.check("진단자 복원", st["expert"] == ME, str(st["expert"]))

    print("\n=== 중복 저장 방지 ===")
    r.check("다시 저장되지 않음(saved=true)", st["saved"] is True, str(st["saved"]))
    page.wait_for_timeout(1200)
    r.check("Firestore 쓰기 발생 없음", page.evaluate("window.__writes.length") == 0,
            str(page.evaluate("window.__writes")))

    print("\n=== 리포트 재발행 ===")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1800)
    body = page.inner_text("#report-dialog")
    r.check("리포트 정상 발행", page.evaluate("document.getElementById('report-dialog').open") is True)
    r.check("리포트에 코멘트 반영", "구두로 전달" in body)
    r.check("리포트에 자가진단 비교표", page.locator("#rpt-compare").count() == 1)
    r.check("사진 없음 안내", "사진" in body, body.replace("\n", " | ")[-200:])
    r.check("막대 정상", page.evaluate("document.querySelectorAll('#rpt-bar .bar-row').length") == 6)

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
