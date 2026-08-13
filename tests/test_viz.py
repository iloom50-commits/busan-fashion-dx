"""차트 시각화를 검증한다.

기존 문제:
  · 레이더 눈금이 꺼져 있어 값을 읽을 수 없었다
  · 막대에 값 라벨이 없고 색이 빨강/초록 이분법이라, 색이 유일한 전달 수단이었다
    (적록색약·흑백 인쇄에서 정보가 사라진다)
  · 가장 중요한 자가진단 대비 전문가 평가가 표로만 있고 그림이 없었다
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, expert_login, fill_self_form, complete_self_diag, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

r = Results()


def open_expert_report(page, with_self=True):
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
    page.fill("#ei-comp", "시각화검증봉제")
    page.click("text=다음 →")
    page.wait_for_selector("text=현장 사진")
    page.click("text=건너뛰기")
    page.wait_for_selector("text=전문가 평가")
    page.evaluate("""(withSelf) => {
        if (withSelf) state.selfScores = {work:3, process:1, quality:3, material:1, basic:3, leader:5};
        const s = {work:2, process:1, quality:2, material:2, basic:3, leader:4};
        Object.keys(s).forEach(k => state.scores[k] = s[k]);
        state.opinion = '검증용'; state.step = 'result'; render();
    }""", with_self)
    page.wait_for_selector("text=전문가 진단 완료")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1500)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    # ================= 전문가 리포트 차트 =================
    print("\n=== 전문가 리포트 · 레이더 ===")
    open_expert_report(page, with_self=True)

    radar = page.evaluate("""() => {
        const c = charts['rpt-radar'];
        if (!c) return null;
        return {
            datasets: c.data.datasets.length,
            labels: c.data.datasets.map(d => d.label),
            ticksShown: c.options.scales.r.ticks.display !== false,
            legendShown: !!(c.options.plugins.legend && c.options.plugins.legend.display !== false),
            colors: c.data.datasets.map(d => d.borderColor)
        };
    }""")
    r.check("레이더에 2계열(자가·전문가)", radar and radar["datasets"] == 2, str(radar))
    r.check("계열 이름 표시", radar and all(radar["labels"]), str(radar and radar["labels"]))
    r.check("레이더 눈금 표시", radar and radar["ticksShown"], str(radar and radar["ticksShown"]))
    r.check("2계열이면 범례 표시", radar and radar["legendShown"], str(radar and radar["legendShown"]))
    r.check("검증 통과한 브랜드색 사용",
            radar and set(c.lower() for c in radar["colors"]) == {"#2563eb", "#16a34a"},
            str(radar and radar["colors"]))

    print("\n=== 전문가 리포트 · 막대 ===")
    bar = page.evaluate("""() => {
        const c = charts['rpt-bar'];
        if (!c) return null;
        const bg = c.data.datasets[0].backgroundColor;
        return {
            colors: bg,
            uniqueColors: [...new Set(bg)].length,
            hasRedGreenPair: bg.includes('#ef4444') && bg.includes('#16a34a'),
            valueLabelPlugin: (c.config.plugins||[]).some(p => p.id === 'valueLabels')
        };
    }""")
    r.check("막대에 값 라벨 플러그인 적용", bar and bar["valueLabelPlugin"], str(bar))
    r.check("빨강/초록 이분법 제거", bar and not bar["hasRedGreenPair"], str(bar and bar["colors"]))
    r.check("점수에 따라 농담이 달라짐(sequential)", bar and bar["uniqueColors"] >= 3,
            str(bar and bar["colors"]))

    print("\n=== 취약 표시 · 등급 게이지 ===")
    body = page.inner_text("#report-dialog")
    r.check("취약 영역을 색이 아닌 글자로도 표시", "취약" in body, body.replace("\n", " | ")[:140])
    r.check("등급 게이지 존재", page.locator("#rpt-gauge").count() == 1)
    if page.locator("#rpt-gauge").count() == 1:
        g = page.inner_text("#rpt-gauge")
        r.check("게이지에 5단계 모두 표시",
                all(f"LV{i}" in g for i in range(1, 6)), g.replace("\n", " | ")[:160])
    else:
        r.check("게이지에 5단계 모두 표시", False, "게이지 없음")

    print("\n=== 자가진단 없을 때 ===")
    open_expert_report(page, with_self=False)
    solo = page.evaluate("""() => {
        const c = charts['rpt-radar'];
        return {datasets: c.data.datasets.length,
                legend: !!(c.options.plugins.legend && c.options.plugins.legend.display !== false)};
    }""")
    r.check("자가진단 없으면 1계열", solo["datasets"] == 1, str(solo))
    r.check("1계열이면 범례 없음", not solo["legend"], str(solo))

    # ================= 자가진단 리포트 차트 =================
    print("\n=== 자가진단 리포트 ===")
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])
    fill_self_form(page)
    complete_self_diag(page)
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(1200)

    sbar = page.evaluate("""() => {
        const c = charts['rpt-bar'];
        const bg = c.data.datasets[0].backgroundColor;
        return {
            hasRedGreenPair: bg.includes('#ef4444') && bg.includes('#3b82f6'),
            uniqueColors: [...new Set(bg)].length,
            valueLabelPlugin: (c.config.plugins||[]).some(p => p.id === 'valueLabels'),
            radarTicks: charts['rpt-radar'].options.scales.r.ticks.display !== false
        };
    }""")
    r.check("자가진단 막대에 값 라벨", sbar["valueLabelPlugin"], str(sbar))
    r.check("자가진단 빨강/파랑 이분법 제거", not sbar["hasRedGreenPair"], str(sbar))
    r.check("자가진단 레이더 눈금 표시", sbar["radarTicks"], str(sbar))
    r.check("자가진단 등급 게이지", page.locator("#rpt-gauge").count() == 1)

    r.check("JS 런타임 에러 없음", len(errs) == 0, str(errs[:3]))
    b.close()

sys.exit(r.summary())
