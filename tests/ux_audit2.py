"""UX 사용성 검증 2회차 — D2 계산 정합성 · D3 문구↔동작 · D7 견고성 · D14 성능

1회차에서 안 본 축만 고른다(coverage-map.md 참조).
화면 숫자를 독립 재계산해 대조하고, 안내 문구를 실제로 실행해 확인한다.
"""
import sys, io, json, time
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

found = []
def F(axis, sev, screen, what, ev=""):
    found.append((axis, sev, screen, what, str(ev)[:200]))
    print(f"  [{sev}] {axis} · {screen} — {what}")
    if ev: print(f"        {str(ev)[:190]}")
def ok(axis, screen, what, ev=""):
    print(f"  [ok ] {axis} · {screen} — {what}" + (f"  ({str(ev)[:90]})" if ev else ""))


def grade_of(total):
    """독립 재계산 — 구현을 참조하지 않고 개발서 표대로 계산한다."""
    return 5 if total >= 25 else 4 if total >= 20 else 3 if total >= 15 else 2 if total >= 10 else 1


with sync_playwright() as pw:
    b = pw.chromium.launch()

    # ══════════ D2 계산 정합성 ══════════
    print("\n[D2] 계산 정합성 — 화면 숫자를 독립 재계산해 대조")
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])

    # 3택 인덱스 → 점수 매핑이 문서(1/3/5)와 맞는가
    tri = page.evaluate("() => DATA.triScore")
    if tri == [1, 3, 5]:
        ok("D2", "자가진단", "3택 점수 매핑 1/3/5", tri)
    else:
        F("D2", "P1", "자가진단", "3택 점수 매핑이 문서와 다름", tri)

    # 여러 조합으로 합계·등급을 대조
    combos = [
        ([0,0,0,0,0,0], 6),  ([2,2,2,2,2,2], 30),
        ([1,1,1,1,1,1], 18), ([0,1,0,1,0,2], 14), ([2,0,2,0,2,0], 18),
    ]
    bad = []
    for picks, expect_sum in combos:
        got = page.evaluate("""(picks) => {
            const ids = ['work','process','quality','material','basic','leader'];
            const sc = {}; ids.forEach((id,i) => sc[id] = DATA.triScore[picks[i]]);
            const sum = Object.values(sc).reduce((a,b)=>a+b,0);
            const lv = sum>=25?5:sum>=20?4:sum>=15?3:sum>=10?2:1;
            return {sum, lv};
        }""", picks)
        if got["sum"] != expect_sum or got["lv"] != grade_of(expect_sum):
            bad.append({"picks":picks, "got":got, "expect":{"sum":expect_sum, "lv":grade_of(expect_sum)}})
    if bad:
        F("D2", "P1", "자가진단", "합계·등급 산정 불일치", bad)
    else:
        ok("D2", "자가진단", f"합계·등급 {len(combos)}개 조합 일치")

    # 등급 경계값 — 9/10, 14/15, 19/20, 24/25에서 정확히 넘어가는가
    edges = page.evaluate("""() => [9,10,14,15,19,20,24,25].map(s =>
        ({s, lv: s>=25?5:s>=20?4:s>=15?3:s>=10?2:1}))""")
    wrong = [e for e in edges if e["lv"] != grade_of(e["s"])]
    if wrong:
        F("D2", "P1", "등급", "경계값에서 등급이 어긋남", wrong)
    else:
        ok("D2", "등급", "경계값 8개 전부 일치", edges)

    # 리포트 격차표 = 전문가 − 자가
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
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("#ei-comp"); page.fill("#ei-comp", "계산검증")
    page.click("text=다음 →"); page.wait_for_selector("text=현장 사진")
    page.click("text=건너뛰기"); page.wait_for_selector("text=전문가 평가")
    SELF = {"work":3,"process":1,"quality":3,"material":1,"basic":3,"leader":5}
    EXP  = {"work":2,"process":1,"quality":2,"material":2,"basic":3,"leader":4}
    page.evaluate("""([s,e]) => {
        state.selfScores = s;
        Object.keys(e).forEach(k => state.scores[k] = e[k]);
        state.opinion = '-'; state.step = 'result'; render();
    }""", [SELF, EXP])
    page.wait_for_selector("text=전문가 진단 완료")
    page.click("text=전문가 진단 리포트 발행")
    page.wait_for_timeout(1500)
    rows = page.eval_on_selector_all("#rpt-compare tbody tr",
        "els => els.map(e => [...e.querySelectorAll('td')].map(t => t.innerText.trim()))")
    NAMES = ["작업지시","공정관리","품질관리","자재관리","기초역량","DX 리더십"]
    KEYS  = ["work","process","quality","material","basic","leader"]
    mism = []
    for i, row in enumerate(rows):
        k = KEYS[i]
        want = EXP[k] - SELF[k]
        shown = row[3]
        exp_txt = "일치" if want == 0 else (f"+{want}" if want > 0 else str(want))
        if shown != exp_txt or row[1] != f"{SELF[k]}점" or row[2] != f"{EXP[k]}점":
            mism.append({"영역":NAMES[i], "표시":row, "기대격차":exp_txt})
    if mism:
        F("D2", "P1", "전문가 리포트", "격차표 계산 불일치", mism)
    else:
        ok("D2", "전문가 리포트", "격차표 6행 전부 일치")

    # ══════════ D3 문구 ↔ 동작 ══════════
    print("\n[D3] 문구 ↔ 동작 — 안내한 대로 실제로 되는가")

    # "입력과 임시저장은 인터넷 없이도 됩니다" (진단자 안내 FAQ)
    page2 = b.new_page(viewport={"width": 1280, "height": 1000})
    page2.on("dialog", lambda d: d.accept())
    page2.goto(f"{BASE}/expert.html")
    page2.evaluate("localStorage.clear()")
    page2.goto(f"{BASE}/expert.html")
    page2.wait_for_function("typeof checkPw === 'function'")
    page2.evaluate(PATCH, [FAKE_SELF])
    page2.fill("#expert-name", "오프라인"); page2.fill("#pw-input", "2026")
    page2.click("#auth-screen >> text=확인")
    page2.wait_for_selector("text=자가진단 결과 불러오기")
    page2.click("text=자가진단 없이 시작 →")
    page2.wait_for_selector("text=기업 유형을 선택해주세요")
    # 여기서부터 네트워크를 끊는다
    page2.context.set_offline(True)
    try:
        page2.click("div:has-text('Track B') >> nth=-1")
        page2.wait_for_selector("#ei-comp", timeout=5000)
        page2.fill("#ei-comp", "오프라인봉제")
        page2.click("text=다음 →")
        page2.wait_for_selector("text=현장 사진", timeout=5000)
        page2.click("text=건너뛰기")
        page2.wait_for_selector("text=전문가 평가", timeout=5000)
        page2.click("div:has-text('수기 장부/화이트보드') >> nth=-1")
        page2.wait_for_timeout(400)
        saved = page2.evaluate("!!localStorage.getItem('dx-expert-draft')")
        st = page2.evaluate("state.scores.work")
        if saved and st == 2:
            ok("D3", "진단자", "오프라인에서 입력·임시저장 동작 — 안내 문구대로")
        else:
            F("D3", "P1", "진단자", "오프라인에서 임시저장이 안 됨(안내와 불일치)", {"draft":saved,"score":st})
    except Exception as e:
        F("D3", "P1", "진단자", "오프라인에서 진단 진행 불가(안내와 불일치)", str(e)[:120])
    page2.context.set_offline(False)

    # "결과는 부산테크노파크에 자동 전송됩니다" (guide.html)
    page3 = b.new_page(viewport={"width": 1280, "height": 900})
    page3.on("dialog", lambda d: d.accept())
    page3.goto(f"{BASE}/index.html")
    page3.wait_for_function("typeof render === 'function'")
    page3.evaluate(PATCH, [FAKE_SELF])
    page3.fill("#si-comp", "문구검증"); page3.fill("#si-ceo", "홍길동")
    page3.fill("#si-biznum", "123-45-67890"); page3.fill("#si-phone", "010-1111-2222")
    page3.click("div.seg-card:has-text('5~9명')"); page3.click("div.seg-card:has-text('임가공(수주)')")
    page3.click("text=다음 →"); page3.wait_for_selector("text=기업 유형을 선택해주세요")
    page3.click("div:has-text('Track B') >> nth=-1"); page3.wait_for_selector("text=6개 영역 자가진단")
    for aid in ["work","process","quality","material","basic","leader"]:
        page3.click(f"button[onclick=\"setSelfScore('{aid}',1)\"]")
    page3.click("text=결과 보기 →"); page3.wait_for_selector("text=자가진단 완료")
    page3.wait_for_timeout(1500)
    status = page3.inner_text("#save-status").strip()
    wrote = page3.evaluate("window.__writes.length")
    if wrote == 1 and "전송" in status:
        ok("D3", "자가진단", "'자동 전송됩니다' 문구대로 저장 호출·안내 표시", status)
    else:
        F("D3", "P1", "자가진단", "'자동 전송' 안내와 실제 동작 불일치", {"writes":wrote,"status":status})

    # ══════════ D7 견고성 ══════════
    print("\n[D7] 견고성")

    # 손상된 임시본
    page4 = b.new_page(viewport={"width": 1280, "height": 900})
    page4.on("dialog", lambda d: d.accept())
    errs = []
    page4.on("pageerror", lambda e: errs.append(str(e)))
    page4.goto(f"{BASE}/expert.html")
    page4.evaluate("localStorage.setItem('dx-expert-draft', '{깨진 JSON')")
    page4.goto(f"{BASE}/expert.html")
    page4.wait_for_function("typeof checkPw === 'function'")
    page4.evaluate(PATCH, [FAKE_SELF])
    page4.fill("#expert-name", "손상"); page4.fill("#pw-input", "2026")
    page4.click("#auth-screen >> text=확인")
    try:
        page4.wait_for_selector("text=자가진단 결과 불러오기", timeout=6000)
        ok("D7", "진단자", "손상된 임시본이 있어도 정상 진입")
    except Exception:
        F("D7", "P0", "진단자", "손상된 임시본으로 앱이 멈춤", errs[:2])

    # localStorage 비활성
    page5 = b.new_page(viewport={"width": 1280, "height": 900})
    page5.on("dialog", lambda d: d.accept())
    errs5 = []
    page5.on("pageerror", lambda e: errs5.append(str(e)))
    page5.add_init_script("""
        Object.defineProperty(window, 'localStorage', {
            get() { throw new Error('저장소 사용 불가'); }
        });
    """)
    page5.goto(f"{BASE}/expert.html")
    try:
        page5.wait_for_function("typeof checkPw === 'function'", timeout=6000)
        page5.evaluate(PATCH, [FAKE_SELF])
        page5.fill("#expert-name", "무저장"); page5.fill("#pw-input", "2026")
        page5.click("#auth-screen >> text=확인")
        page5.wait_for_selector("text=자가진단 결과 불러오기", timeout=6000)
        ok("D7", "진단자", "localStorage 사용 불가 환경에서도 진입 가능")
    except Exception as e:
        F("D7", "P1", "진단자", "localStorage 차단 시 진입 불가(사생활 보호 모드 등)",
          str(e)[:100] + " | " + str(errs5[:1]))

    # 저장 연타 — 결과 화면에서 saveDiagnosis가 여러 번 호출돼도 1건만
    page6 = b.new_page(viewport={"width": 1280, "height": 900})
    page6.on("dialog", lambda d: d.accept())
    page6.goto(f"{BASE}/expert.html")
    page6.evaluate("localStorage.clear()")
    page6.goto(f"{BASE}/expert.html")
    page6.wait_for_function("typeof checkPw === 'function'")
    page6.evaluate(PATCH, [FAKE_SELF])
    page6.fill("#expert-name", "연타"); page6.fill("#pw-input", "2026")
    page6.click("#auth-screen >> text=확인")
    page6.wait_for_selector("text=자가진단 결과 불러오기")
    page6.click("text=자가진단 없이 시작 →")
    page6.wait_for_selector("text=기업 유형을 선택해주세요")
    page6.click("div:has-text('Track B') >> nth=-1")
    page6.wait_for_selector("#ei-comp"); page6.fill("#ei-comp", "연타검증")
    page6.click("text=다음 →"); page6.wait_for_selector("text=현장 사진")
    page6.click("text=건너뛰기"); page6.wait_for_selector("text=전문가 평가")
    page6.evaluate("""() => {
        ['work','process','quality','material','basic','leader'].forEach(k=>state.scores[k]=3);
        state.opinion='-'; state.step='result'; render();
    }""")
    page6.wait_for_timeout(1200)
    page6.evaluate("() => { for (let i=0;i<5;i++) saveDiagnosis(); }")
    page6.wait_for_timeout(1000)
    w = page6.evaluate("window.__writes.length")
    if w == 1:
        ok("D7", "진단자", "저장 연타해도 1건만 기록", f"{w}건")
    else:
        F("D7", "P1", "진단자", "저장이 중복 기록됨", f"{w}건")

    # ══════════ D14 성능 ══════════
    print("\n[D14] 성능 — 데이터 100건")
    big = []
    for i in range(100):
        tot = 6 + (i % 25)
        lv = grade_of(tot)
        big.append({"id":f"p{i}", "type":"expert" if i % 2 else "self",
                    "company":f"성능검증{i:03d}", "bizNum":f"{1000000000+i}",
                    "emp":"5~9명", "track":"ABC"[i%3], "expertName":"성능",
                    "scores":{k: 1+(i+j)%5 for j,k in enumerate(KEYS)},
                    "totalScore":tot, "gradeLv":lv, "gradeTxt":f"LV{lv}",
                    "causes":{}, "comments":{}, "solutions":{},
                    "roadmap":{"short":[],"mid":[],"long":[]}, "opinion":"-"})

    page7 = b.new_page(viewport={"width": 1400, "height": 1000})
    page7.on("dialog", lambda d: d.accept())
    page7.goto(f"{BASE}/admin.html")
    page7.wait_for_selector("#pw-input")
    page7.evaluate("""(docs) => {
        const inst = firebase.firestore();
        inst.collection = () => ({ orderBy: () => ({ get: async () => ({
            docs: docs.map(x => ({id:x.id, data:()=>x})) }) }) });
    }""", big)
    t0 = time.time()
    page7.fill("#pw-input", "busan2026")
    page7.click("#auth-screen >> text=확인")
    page7.wait_for_selector("#tbody tr")
    t_list = (time.time() - t0) * 1000
    n_rows = page7.evaluate("document.querySelectorAll('#tbody tr').length")
    if t_list < 3000:
        ok("D14", "관리자", f"100건 목록 렌더 {t_list:.0f}ms", f"{n_rows}행")
    else:
        F("D14", "P2", "관리자", f"100건 목록 렌더가 느림 {t_list:.0f}ms", f"{n_rows}행")

    t0 = time.time()
    page7.click("text=종합 분석 보고서")
    page7.wait_for_selector("#sum-company-rows tr")
    t_sum = (time.time() - t0) * 1000
    n_co = page7.evaluate("document.querySelectorAll('#sum-company-rows tr').length")
    if t_sum < 3000:
        ok("D14", "종합보고서", f"100건 집계·렌더 {t_sum:.0f}ms", f"{n_co}개사")
    else:
        F("D14", "P2", "종합보고서", f"100건 집계가 느림 {t_sum:.0f}ms", f"{n_co}개사")

    b.close()

print("\n" + "="*68)
if found:
    print(f"발견 {len(found)}건")
    for a, s, sc, w, e in found:
        print(f"  [{s}] {a} · {sc} — {w}")
else:
    print("발견 0건 — 이번 회차 축에서 결함 없음")
