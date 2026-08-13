"""전문가 진단에서 Track B를 기본으로 안내하는지 검증한다.

근거
  개발서 Ⅲ-1: "봉제(임가공) 공장은 Track B(전문 제조사)를 기본 적용한다"
  과업지시서 66행: "봉제 제조사는 Track B 기본 적용"

D12(설계↔구현 대조)에서 발견: 자가진단에는 매출형태 기반 권장 표시가 있으나
전문가 진단에는 아무 안내가 없어 진단자가 매번 맨눈으로 골랐다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()

# 자가진단에서 Track A를 고른 기업 — 자가진단 값이 기본 안내보다 우선해야 한다
FAKE_A = dict(FAKE_SELF)
FAKE_A["id"] = "selfA"
FAKE_A["company"] = "에이봉제"
FAKE_A["track"] = "A"
FAKE_A["bizNum"] = "9998887777"


def to_track(page, fakes, skip=True):
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof checkPw === 'function'")
    page.evaluate(PATCH, fakes)
    expert_login(page)
    if skip:
        page.click("text=자가진단 없이 시작 →")
        page.wait_for_selector("text=기업 유형을 선택해주세요")
    # skip=False면 조회 화면에 머문다 — 호출한 쪽이 조회 후 Track 화면으로 넘어간다


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ===== 자가진단 없이 시작한 경우 — Track B 기본 안내 =====
    print("\n=== 자가진단 없이 시작 ===")
    to_track(page, [FAKE_SELF])
    wiz = page.inner_text("#wiz")
    r.check("Track B 기본 안내 문구", "봉제" in wiz and "기본" in wiz, wiz.replace("\n", " | ")[:160])

    marked = page.eval_on_selector_all(
        ".track-card", "els => els.map(e => ({t: e.getAttribute('data-track'), rec: e.classList.contains('recommended')}))")
    b_rec = [m for m in marked if m["t"] == "B" and m["rec"]]
    other = [m for m in marked if m["t"] != "B" and m["rec"]]
    r.check("Track B 카드에 기본 표시", len(b_rec) == 1, str(marked))
    r.check("다른 Track에는 표시 없음", len(other) == 0, str(marked))

    # ===== 자가진단이 있으면 그 값이 우선 =====
    print("\n=== 자가진단 Track A 기업 ===")
    to_track(page, [FAKE_A], skip=False)
    page.fill("#lk-biznum", "999-88-87777")
    page.click("#wiz >> text=조회")
    page.wait_for_selector("text=이 결과로 시작 →", timeout=8000)
    page.click("#lk-result >> text=이 결과로 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")

    wiz2 = page.inner_text("#wiz")
    marked2 = page.eval_on_selector_all(
        ".track-card", "els => els.map(e => ({t: e.getAttribute('data-track'), rec: e.classList.contains('recommended')}))")
    a_rec = [m for m in marked2 if m["t"] == "A" and m["rec"]]
    b_rec2 = [m for m in marked2 if m["t"] == "B" and m["rec"]]
    r.check("자가진단 Track A가 표시됨", len(a_rec) == 1, str(marked2))
    r.check("자가진단이 있으면 B 기본 안내는 안 뜸", len(b_rec2) == 0, str(marked2))
    r.check("자가진단 선택값 문구 표시", "자가진단 시 선택: Track A" in wiz2, wiz2.replace("\n", " | ")[:140])

    # ===== 선택은 여전히 자유 =====
    print("\n=== 선택 자유 ===")
    page.click("div:has-text('Track C') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    r.check("안내와 다른 Track도 선택 가능", page.evaluate("state.track") == "C",
            page.evaluate("state.track"))

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
