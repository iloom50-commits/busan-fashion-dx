"""자가진단 리포트 내용을 검증한다.

기존 문제:
  · 응답 내역이 없어 대표자가 무엇을 골랐는지 보고서에 남지 않았다
  · 요약이 등급별 고정 문장이라, 등급이 같은 기업은 완전히 같은 문장을 받았다
  · RFP가 솔루션 이름 한 줄뿐이었다
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()


def run_self(page, picks, comp="자가검증봉제"):
    """picks: [(영역id, 선택인덱스)] — 0:미도입 1:일부도입 2:적극활용"""
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    page.fill("#si-comp", comp)
    page.fill("#si-ceo", "홍길동")
    page.fill("#si-biznum", "123-45-67890")
    page.fill("#si-phone", "010-1111-2222")
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in picks:
        page.click(f"button[onclick=\"setSelfScore('{aid}',{idx})\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(1200)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # 작업지시 미도입 / 공정 일부 / 품질 미도입 / 자재 일부 / 기초 미도입 / 리더십 적극
    A = [("work",0), ("process",1), ("quality",0), ("material",1), ("basic",0), ("leader",2)]
    print("\n=== 응답 내역 ===")
    run_self(page, A)

    r.check("응답 내역 섹션", page.locator("#rpt-answers").count() == 1)
    ans = page.inner_text("#rpt-answers") if page.locator("#rpt-answers").count() else ""
    r.check("6개 영역 모두 표시",
            all(x in ans for x in ["작업지시", "공정관리", "품질관리", "자재관리", "기초역량", "DX 리더십"]),
            ans.replace("\n", " | ")[:180])
    r.check("선택한 단계 문구 표시", "미도입" in ans and "일부 도입" in ans and "적극 활용" in ans,
            ans.replace("\n", " | ")[:180])
    r.check("영역별 점수 표시", "1점" in ans and "3점" in ans and "5점" in ans,
            ans.replace("\n", " | ")[:180])

    print("\n=== 요약이 응답에 따라 달라지는가 ===")
    sum1 = page.inner_text("#rpt-comment")
    r.check("요약에 취약 영역명이 들어감",
            any(n in sum1 for n in ["작업지시", "품질관리", "기초역량"]), sum1[:180])

    # 같은 등급(14점)이지만 취약 영역이 다른 조합
    B = [("work",2), ("process",0), ("quality",1), ("material",0), ("basic",1), ("leader",0)]
    run_self(page, B, comp="자가검증봉제2")
    sum2 = page.inner_text("#rpt-comment")
    lv1 = page.evaluate("state.grade.lv")
    r.check("두 번째 진단도 동일 등급", lv1 == 2, f"lv={lv1}")
    r.check("취약 영역이 다르면 요약도 달라짐", sum1 != sum2,
            f"1: {sum1[:70]}\n              2: {sum2[:70]}")

    print("\n=== RFP 상세 ===")
    rfp = page.inner_text("#rpt-rfp")
    r.check("RFP에 솔루션 설명", "메신저" in rfp or "기록" in rfp or "관리" in rfp,
            rfp.replace("\n", " | ")[:180])
    r.check("RFP에 예산", "만" in rfp or "무료" in rfp, rfp.replace("\n", " | ")[:180])
    r.check("RFP에 도입 시기", "단기" in rfp or "중기" in rfp, rfp.replace("\n", " | ")[:180])

    r.check("등급 게이지 유지", page.locator("#rpt-gauge").count() == 1)
    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
