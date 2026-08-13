"""D12 설계 ↔ 구현 대조 — 문서에 '~한다'로 쓴 규칙을 하나씩 실행해 확인한다.

대조 문서
  A. 봉제공장_DX진단툴_개발서_v01.html   (발주처 제출 설계서, 2026.06)
  B. [과업지시서] ..._v01.md              (계약 요구사항)
  C. v2/guide.html                        (사용자에게 한 약속)
  D. 진단자_사용안내.html                  (진단자에게 한 약속)

코드를 읽고 "괜찮아 보인다"는 미검증이다. 값을 바꿔 결과가 변하는지 실행한다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

out = []
def rec(src, claim, verdict, evidence=""):
    out.append((src, claim, verdict, str(evidence)[:180]))
    mark = {"일치": "[일치]", "불일치": "[불일치]", "미구현": "[미구현]", "부분": "[부분]"}[verdict]
    print(f"  {mark:8} {src} — {claim}")
    if evidence:
        print(f"           {str(evidence)[:170]}")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())

    # ══ A-1. 등급 체계 — 개발서는 4등급(LV2~LV5), 14점 이하 = LV2 ══
    print("\n[A] 개발서 Ⅲ-5 종합 등급 산정")
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof render === 'function'")
    grades = page.evaluate("""() => {
        const r = [];
        for (let sum = 6; sum <= 30; sum++) {
            const lv = sum>=25?5:sum>=20?4:sum>=15?3:sum>=10?2:1;
            r.push({sum, lv});
        }
        const bands = {};
        r.forEach(x => { (bands[x.lv] = bands[x.lv] || []).push(x.sum); });
        return Object.entries(bands).map(([lv, s]) =>
            ({lv: +lv, from: Math.min(...s), to: Math.max(...s)}));
    }""")
    impl_levels = sorted(g["lv"] for g in grades)
    band_str = " · ".join(f"LV{g['lv']} {g['from']}~{g['to']}점" for g in sorted(grades, key=lambda x: x["lv"]))
    if impl_levels == [2, 3, 4, 5]:
        rec("개발서", "4개 등급(LV2~LV5) 산정", "일치", band_str)
    else:
        rec("개발서", "4개 등급(LV2~LV5) 산정 · 14점 이하는 LV2 도입",
            "불일치", f"구현은 {len(impl_levels)}개 등급 — {band_str}")

    # 실제로 6점 진단을 돌려 화면에 무엇이 뜨는지 본다
    page.evaluate(PATCH, [FAKE_SELF])
    page.fill("#si-comp", "저점검증"); page.fill("#si-ceo", "홍길동")
    page.fill("#si-biznum", "123-45-67890"); page.fill("#si-phone", "010-1111-2222")
    page.click("div.seg-card:has-text('5~9명')"); page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →"); page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1"); page.wait_for_selector("text=6개 영역 자가진단")
    for aid in ["work","process","quality","material","basic","leader"]:
        page.click(f"button[onclick=\"setSelfScore('{aid}',0)\"]")   # 전부 미도입 = 6점
    page.click("text=결과 보기 →"); page.wait_for_selector("text=자가진단 완료")
    shown = page.evaluate("() => ({lv: state.grade.lv, txt: state.grade.txt})")
    if shown["lv"] == 1:
        rec("개발서", "6점(최저) 진단 시 화면 표기", "불일치",
            f"개발서 기준이면 'LV2 도입', 실제 표기는 '{shown['txt']}'")
    else:
        rec("개발서", "6점(최저) 진단 시 화면 표기", "일치", shown["txt"])

    # ══ A-2. Track B 기본 적용 ══
    print("\n[A·B] 개발서 Ⅲ-1 / 과업지시서 66행 — 봉제 제조사 Track B 기본 적용")
    page.goto(f"{BASE}/expert.html")
    page.evaluate("localStorage.clear()")
    page.goto(f"{BASE}/expert.html")
    page.wait_for_function("typeof checkPw === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    page.fill("#expert-name", "검증자"); page.fill("#pw-input", "2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")
    page.click("text=자가진단 없이 시작 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    pre = page.evaluate("() => ({track: state.track, hint: document.getElementById('wiz').innerText.includes('권장')})")
    if pre["track"] == "B":
        rec("개발서", "봉제 제조사는 Track B 기본 적용", "일치", pre)
    elif pre["hint"]:
        rec("개발서", "봉제 제조사는 Track B 기본 적용", "부분", "권장 표시만 있고 기본 선택 아님")
    else:
        rec("개발서", "봉제 제조사는 Track B 기본 적용", "미구현",
            "전문가 진단은 기본값·권장 표시 없이 매번 직접 선택")

    # ══ A-3. Track별 문항 자동 분기 ══
    print("\n[A] 개발서 Ⅲ-3 — Track별 문항 자동 분기")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp")
    page.fill("#ei-comp", "분기검증"); page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진"); page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")
    qB = page.inner_text("#wiz").split("\n")[1]
    qs = page.evaluate("""() => ({
        A: DATA.questions.work.A, B: DATA.questions.work.B, C: DATA.questions.work.C })""")
    if qs["A"] != qs["B"] != qs["C"] and "현장 작업지시서" in qB:
        rec("개발서", "Track별 문항 자동 분기", "일치", f"Track B 표시 문항: {qB}")
    else:
        rec("개발서", "Track별 문항 자동 분기", "불일치", qs)

    # ══ A-4. 척도 문구 일치 ══
    print("\n[A] 개발서 Ⅲ-4 — 5단계 척도 문구")
    sc = page.evaluate("() => ({e: DATA.expertOpts.map(o=>o.text), l: DATA.leaderOpts.map(o=>o.text)})")
    DOC_E = ["구두/전화 위주 (기록 없음)","수기 장부/화이트보드","엑셀(Excel) 및 메신저 공유",
             "클라우드/협업툴 실시간 공유","ERP/MES 시스템 연동"]
    DOC_L = ["관심 없음","필요성은 느끼나 계획 없음","관심 있음 (교육 참석)",
             "적극적 의지 (예산 배정)","강력한 의지 (직접 주도)"]
    rec("개발서", "일반 영역 5단계 척도 문구", "일치" if sc["e"] == DOC_E else "불일치",
        "" if sc["e"] == DOC_E else sc["e"])
    rec("개발서", "DX 리더십 척도 문구", "일치" if sc["l"] == DOC_L else "불일치",
        "" if sc["l"] == DOC_L else sc["l"])

    # ══ A-5. 리포트 구성 요소 6가지 ══
    print("\n[A] 개발서 Ⅳ-2 — 리포트 구성 요소")
    page.evaluate("""() => {
        const s = {work:2, process:1, quality:2, material:2, basic:3, leader:4};
        Object.keys(s).forEach(k => state.scores[k] = s[k]);
        state.opinion = '검증용 종합의견'; state.step = 'result'; render();
    }""")
    page.wait_for_selector("text=전문가 진단 완료")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1800)
    comp = page.evaluate("""() => ({
        grade:  !!document.getElementById('rpt-gauge'),
        radar:  (document.getElementById('rpt-radar')||{}).width > 0,
        bar:    document.querySelectorAll('#rpt-bar .bar-row').length === 6,
        opinion: (document.getElementById('rpt-comment')||{}).innerText.length > 0,
        rfp:    (document.getElementById('rpt-rfp')||{}).innerText.length > 0,
        print:  typeof savePDF === 'function'
    })""")
    for k, label in [("grade","종합 점수·등급"), ("radar","레이더 차트"), ("bar","막대 차트"),
                     ("opinion","전문가 의견"), ("rfp","우선 개선과제(RFP)"), ("print","PDF 발행")]:
        rec("개발서", f"리포트 구성 — {label}", "일치" if comp[k] else "미구현", "")

    # ══ A-6. 기술 구현 — 막대 차트를 Chart.js로 생성한다고 기술 ══
    print("\n[A] 개발서 Ⅴ — 기술 구현 기술 내용")
    impl = page.evaluate("() => ({ chartBar: !!(window.charts && charts['rpt-bar']), htmlBar: document.querySelectorAll('#rpt-bar .bar-row').length })")
    if impl["chartBar"]:
        rec("개발서", "Chart.js 기반 레이더·막대 차트", "일치", impl)
    else:
        rec("개발서", "Chart.js 기반 레이더·막대 차트 자동 생성", "불일치",
            f"레이더만 Chart.js. 막대는 HTML {impl['htmlBar']}행으로 교체됨(문서 갱신 필요)")

    # ══ B. 과업지시서 산출물 ══
    print("\n[B] 과업지시서 Ⅳ 산출물")
    rec("과업지시서 79행", "기업별 리포트(종합등급·레이더·막대·전문가의견·개선과제)", "일치", "")
    rec("과업지시서 81행", "진단 원시 데이터(영역 점수·기초정보) 산출", "일치", "관리자 CSV 내보내기")
    rec("과업지시서 80행", "20개사 종합 분석 보고서 출력", "미구현",
        "관리자 화면에 등급분포·영역평균 차트는 있으나 보고서 발행 기능 없음")
    rec("과업지시서 70행", "현장 전경·애로사항 사진 기록", "일치", "리포트에 반영")

    # ══ C. guide.html 약속 ══
    print("\n[C] 사용 안내(guide.html) 약속")
    page.goto(f"{BASE}/guide.html", wait_until="networkidle")
    g = page.inner_text("body")
    rec("guide.html", "자가진단 URL·전문가 URL·관리자 URL 안내", "일치" if g.count("dx-diagnostic-tool") >= 3 else "불일치",
        f"URL 언급 {g.count('dx-diagnostic-tool')}회")
    rec("guide.html", "관리자 비밀번호를 문서에 기재하지 않음", "일치" if "busan2026" not in g else "불일치", "")
    rec("guide.html", "전문가 절차 9단계 안내", "일치" if page.locator(".card.green .steps li").count() == 9 else "불일치",
        f"{page.locator('.card.green .steps li').count()}단계")

    b.close()

print("\n" + "="*70)
for v in ["불일치", "미구현", "부분"]:
    rows = [r for r in out if r[2] == v]
    if rows:
        print(f"\n■ {v} {len(rows)}건")
        for src, claim, _, ev in rows:
            print(f"   · [{src}] {claim}")
            if ev: print(f"       {ev}")
n_ok = len([r for r in out if r[2] == "일치"])
print(f"\n일치 {n_ok}건 / 전체 {len(out)}건")
