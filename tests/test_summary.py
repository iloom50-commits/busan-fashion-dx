"""관리자 종합 분석 보고서를 검증한다.

근거 — 과업지시서 76행: "20개사 전체 결과를 종합한 부산 봉제 소공인 DX 성숙도
현황 분석(영역별·등급별 분포 등)", 80행: "20개사 종합 분석 보고서(최종 결과보고서)"

D12(설계↔구현 대조)에서 유일하게 남은 과업 산출물 공백으로 확인됐다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()


def doc(i, typ, comp, biz, track, scores, expert=None):
    tot = sum(scores.values())
    lv = 5 if tot >= 25 else 4 if tot >= 20 else 3 if tot >= 15 else 2 if tot >= 10 else 1
    d = {"id": f"{typ}{i}", "type": typ, "company": comp, "bizNum": biz, "track": track,
         "emp": "5~9명", "scores": scores, "totalScore": tot, "gradeLv": lv,
         "gradeTxt": f"LV{lv}. " + {1:"기초",2:"도입",3:"정착",4:"고도화",5:"선도"}[lv]}
    if typ == "expert":
        d["expertName"] = expert or "나윤정"
        d["solutions"] = {"work": ["w1"], "quality": ["q1"]}
        d["causes"] = {}; d["comments"] = {}
        d["roadmap"] = {"short": ["w1"], "mid": [], "long": []}
        d["opinion"] = "-"
    return d


S = lambda a,b,c,d,e,f: {"work":a,"process":b,"quality":c,"material":d,"basic":e,"leader":f}

# 3개사: A사(자가+전문가), B사(전문가만), C사(자가만)
DOCS = [
    doc(1, "self",   "가봉제", "1111111111", "B", S(3,1,3,1,3,5)),   # 16 LV3
    doc(1, "expert", "가봉제", "1111111111", "B", S(2,1,2,2,3,4)),   # 14 LV2
    doc(2, "expert", "나봉제", "2222222222", "B", S(1,1,1,1,2,2)),   # 8  LV1
    doc(3, "self",   "다봉제", "3333333333", "A", S(5,5,5,3,5,5)),   # 28 LV5
]

STUB = """(docs) => {
    const inst = firebase.firestore();
    inst.collection = () => ({ orderBy: () => ({ get: async () => ({
        docs: docs.map(x => ({ id: x.id, data: () => x })) }) }) });
}"""


def open_admin(page, docs):
    page.goto(f"{BASE}/admin.html")
    page.wait_for_selector("#pw-input")
    page.evaluate(STUB, docs)
    page.fill("#pw-input", "busan2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_timeout(1200)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    print("\n=== 보고서 발행 ===")
    open_admin(page, DOCS)
    r.check("종합 분석 보고서 버튼 존재", page.locator("text=종합 분석 보고서").count() >= 1)

    page.click("text=종합 분석 보고서")
    page.wait_for_timeout(1200)
    r.check("보고서 다이얼로그 열림",
            page.evaluate("() => { const d=document.getElementById('sum-dialog'); return d && d.open; }") is True)
    body = page.inner_text("#sum-dialog") if page.locator("#sum-dialog").count() else ""

    print("\n=== 기업 단위 집계 ===")
    # 진단 기록은 4건이지만 기업은 3개사다
    n = page.evaluate("document.querySelectorAll('#sum-company-rows tr').length")
    r.check("기업별 요약표 3개사", n == 3, f"행 {n}개")
    r.check("진단 건수가 아닌 기업 수로 집계", "3개사" in body, body.replace("\n", " | ")[:200])
    r.check("전문가 진단이 있으면 그 결과를 대표값으로",
            "14" in page.inner_text("#sum-company-rows") and "16" not in page.inner_text("#sum-company-rows").split("가봉제")[1][:40],
            page.inner_text("#sum-company-rows").replace("\n", " | ")[:160])

    print("\n=== 등급·영역 분포 ===")
    r.check("등급별 분포 5단계 전부", page.locator("#sum-grade .bar-row").count() == 5,
            str(page.locator("#sum-grade .bar-row").count()))
    r.check("영역별 평균 6영역", page.locator("#sum-area .bar-row").count() == 6,
            str(page.locator("#sum-area .bar-row").count()))
    r.check("Track별 분포 표시", page.locator("#sum-track").count() == 1)

    print("\n=== 격차·개선과제 ===")
    r.check("자가진단 대비 격차 분석", page.locator("#sum-gap").count() == 1)
    gap = page.inner_text("#sum-gap") if page.locator("#sum-gap").count() else ""
    r.check("격차 분석은 둘 다 있는 기업만", "1개사" in gap, gap.replace("\n", " | ")[:160])
    r.check("우선 개선과제 집계", page.locator("#sum-rfp").count() == 1)

    print("\n=== 출력 ===")
    r.check("PDF 저장 버튼", page.locator("#sum-dialog >> text=PDF로 저장").count() == 1)
    r.check("작성일 표기", "2026" in body)
    r.check("발주기관 표기", "부산테크노파크" in body)

    print("\n=== 데이터가 없을 때 ===")
    page.evaluate("document.getElementById('sum-dialog').close()")
    open_admin(page, [])
    page.click("text=종합 분석 보고서")
    page.wait_for_timeout(800)
    empty = page.inner_text("#sum-dialog") if page.locator("#sum-dialog").count() else ""
    r.check("빈 데이터 안내", "없습니다" in empty or "0개사" in empty, empty.replace("\n", " | ")[:140])

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
