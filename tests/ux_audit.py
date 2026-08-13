"""UX 사용성 검증 1회차 — 배포본 실측.

축: D1 죽은 컨트롤 · D4 상태 완결성 · D6 입력 경계값 · D8 반응형 · D9 접근성 · D11 권한 경계

프로덕션에 기록이 남지 않도록 Firestore 쓰기를 가로챈다.
읽기는 실제를 쓴다(라이브 화면을 봐야 하므로).
"""
import sys, io, json
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
LIVE = "https://dx-diagnostic-tool.vercel.app"

BLOCK = """() => {
    const inst = firebase.firestore();
    const orig = inst.collection.bind(inst);
    window.__writes = [];
    inst.collection = (name) => {
        const ref = orig(name);
        return new Proxy(ref, { get(t,p) {
            if (p === 'add') return async (d) => { window.__writes.push(d); return {id:'blocked'}; };
            const v = t[p];
            return typeof v === 'function' ? v.bind(t) : v;
        }});
    };
}"""

findings = []
def F(axis, sev, screen, what, evidence=""):
    findings.append({"axis":axis, "sev":sev, "screen":screen, "what":what, "ev":str(evidence)[:300]})
    print(f"  [{sev}] {axis} · {screen} — {what}")
    if evidence:
        print(f"        근거: {str(evidence)[:200]}")

def ok(axis, screen, what):
    print(f"  [ok ] {axis} · {screen} — {what}")


# ── D1: 죽은 컨트롤 — onclick이 가리키는 함수가 실제로 있는가 ──────────────
def d1_dead_controls(page, screen):
    res = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('[onclick]').forEach(el => {
            const code = el.getAttribute('onclick');
            // 함수 호출 이름만 뽑는다 (obj.method(...) 형태 포함)
            const names = [...code.matchAll(/([A-Za-z_$][\\w$]*)\\s*\\(/g)].map(m => m[1]);
            names.forEach(n => {
                if (['if','for','while','switch','return','function','event'].includes(n)) return;
                if (typeof window[n] === 'undefined' && !code.includes(n + '.')) {
                    // window에 없고 메서드 호출도 아니면 후보
                    out.push({text: (el.innerText||'').trim().slice(0,24), fn: n, code: code.slice(0,80)});
                }
            });
        });
        return out;
    }""")
    # document.getElementById(...) 같은 내장은 제외
    builtins = {"document","window","getElementById","querySelector","JSON","Math","Number","String","Date","confirm","alert"}
    dead = [r for r in res if r["fn"] not in builtins]
    if dead:
        F("D1", "P1", screen, f"핸들러가 없는 onclick {len(dead)}건", dead[:5])
    else:
        ok("D1", screen, f"onclick 핸들러 전부 존재")


# ── D8: 반응형 — 가로 넘침 ────────────────────────────────────────────
def d8_overflow(page, screen, w):
    o = page.evaluate("""() => {
        const d = document.documentElement;
        const wide = [...document.querySelectorAll('body *')]
            .filter(e => e.getBoundingClientRect().right > d.clientWidth + 2)
            .slice(0,6)
            .map(e => ({tag:e.tagName, cls:(e.className||'').toString().slice(0,40),
                        right: Math.round(e.getBoundingClientRect().right),
                        txt:(e.innerText||'').trim().slice(0,24)}));
        return {scrollW: d.scrollWidth, clientW: d.clientWidth, wide};
    }""")
    if o["scrollW"] > o["clientW"] + 2:
        F("D8", "P1", f"{screen}@{w}px", f"가로 스크롤 발생 ({o['scrollW']} > {o['clientW']})", o["wide"])
    else:
        ok("D8", f"{screen}@{w}px", "가로 넘침 없음")


# ── D9: 접근성 — 터치 타겟 크기 ───────────────────────────────────────
def d9_touch(page, screen, w):
    small = page.evaluate("""() => [...document.querySelectorAll('button, [onclick]')]
        .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 32; })
        .slice(0,8)
        .map(e => ({txt:(e.innerText||'').trim().slice(0,20), h: Math.round(e.getBoundingClientRect().height)}))""")
    if small:
        F("D9", "P2", f"{screen}@{w}px", f"터치 타겟 32px 미만 {len(small)}건", small)
    else:
        ok("D9", f"{screen}@{w}px", "터치 타겟 32px 이상")


with sync_playwright() as pw:
    b = pw.chromium.launch()

    # ══════════ D11 권한 경계 ══════════
    print("\n[D11] 권한 경계 — 로그인 전 접근")
    page = b.new_page(viewport={"width":1280,"height":900})
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_timeout(600)
    st = page.evaluate("""() => ({
        wiz: (document.getElementById('wiz')||{}).innerText || '',
        authShown: !document.getElementById('auth-screen').classList.contains('hidden'),
        // 로그인 없이 진단 데이터를 읽을 수 있는가
    })""")
    if st["wiz"].strip():
        F("D11", "P1", "expert.html", "로그인 전에 진단 화면 내용이 노출됨", st["wiz"][:80])
    else:
        ok("D11", "expert.html", "로그인 전 화면 비어 있음")

    peek = page.evaluate("""async () => {
        try { const s = await firebase.firestore().collection('diagnoses').get();
              return {n: s.size, sample: s.docs.slice(0,1).map(d=>d.data().company)}; }
        catch(e) { return {err: e.message}; }
    }""")
    if peek.get("n", 0) > 0:
        F("D11", "P2", "expert.html", "로그인 없이도 콘솔에서 진단 데이터 조회 가능(설계상 수용된 결정)", peek)
    page.close()

    page = b.new_page(viewport={"width":1280,"height":900})
    page.goto(f"{LIVE}/admin.html", wait_until="networkidle")
    page.wait_for_timeout(500)
    a = page.evaluate("""() => ({
        app: document.getElementById('app').classList.contains('hidden'),
        rows: document.querySelectorAll('#tbody tr').length
    })""")
    if not a["app"] or a["rows"] > 0:
        F("D11", "P1", "admin.html", "비밀번호 전에 대시보드 내용 노출", a)
    else:
        ok("D11", "admin.html", "비밀번호 전 대시보드 숨김")
    page.close()

    # ══════════ D1 · D8 · D9 : 화면별 ══════════
    for name, url, setup in [
        ("자가진단-입력", "/", None),
        ("진단자-로그인", "/expert.html", None),
        ("관리자-로그인", "/admin.html", None),
    ]:
        print(f"\n[D1/D8/D9] {name}")
        for w, h in [(1280, 900), (768, 1024), (360, 800)]:
            page = b.new_page(viewport={"width":w, "height":h})
            page.goto(f"{LIVE}{url}", wait_until="networkidle")
            page.wait_for_timeout(700)
            if w == 1280:
                d1_dead_controls(page, name)
            d8_overflow(page, name, w)
            if w == 360:
                d9_touch(page, name, w)
            page.close()

    # ══════════ D6 입력 경계값 ══════════
    print("\n[D6] 입력 경계값 — 자가진단 폼")
    page = b.new_page(viewport={"width":1280,"height":1000})
    page.on("dialog", lambda d: d.accept())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{LIVE}/", wait_until="networkidle")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(BLOCK)

    EVIL = '<b>굵게</b> & "따옴표" <script>x</script> 아주긴이름' + '가' * 60
    page.fill("#si-comp", EVIL)
    page.fill("#si-ceo", "홍길동<img src=x onerror=alert(1)>")
    page.fill("#si-biznum", "123-45-67890")
    page.fill("#si-phone", "010-1111-2222")
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")
    page.wait_for_selector("text=기업 유형을 선택해주세요")
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in [("work",0),("process",1),("quality",0),("material",1),("basic",0),("leader",2)]:
        page.click(f"button[onclick=\"setSelfScore('{aid}',{idx})\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")
    page.click("text=결과보고서 출력 (PDF)")
    page.wait_for_timeout(1200)

    inj = page.evaluate("""() => {
        const info = document.getElementById('rpt-info');
        return {
            boldTags: info.querySelectorAll('b').length,
            imgTags: info.querySelectorAll('img').length,
            scriptTags: info.querySelectorAll('script').length,
            text: info.innerText.slice(0,120)
        };
    }""")
    if inj["imgTags"] or inj["scriptTags"] or inj["boldTags"]:
        F("D6", "P1", "자가진단 리포트",
          "기업명·대표자의 HTML이 그대로 해석됨(이스케이프 누락)", inj)
    else:
        ok("D6", "자가진단 리포트", "HTML 이스케이프 처리됨")

    ov = page.evaluate("""() => {
        const d = document.getElementById('report-dialog');
        return {scrollW: d.scrollWidth, clientW: d.clientWidth};
    }""")
    if ov["scrollW"] > ov["clientW"] + 2:
        F("D6", "P2", "자가진단 리포트", "긴 기업명으로 리포트 가로 넘침", ov)
    else:
        ok("D6", "자가진단 리포트", "긴 입력에도 가로 넘침 없음")

    if errs:
        F("D6", "P1", "자가진단", "JS 런타임 에러 발생", errs[:3])
    page.close()

    # ══════════ D4 상태 완결성 ══════════
    print("\n[D4] 상태 완결성 — 조회 실패 / 빈 목록")
    page = b.new_page(viewport={"width":1280,"height":1000})
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof checkPw === 'function'")
    # Firestore 조회를 실패시킨다
    page.evaluate("""() => {
        const inst = firebase.firestore();
        inst.collection = () => ({
            add: async () => ({id:'x'}),
            where: () => ({ get: async () => { throw new Error('네트워크 연결 없음'); } })
        });
    }""")
    page.fill("#expert-name", "검증자"); page.fill("#pw-input", "2026")
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")
    page.wait_for_timeout(1500)
    s = page.evaluate("""() => ({
        list: (document.getElementById('lk-list')||{}).innerText || '',
        done: (document.getElementById('lk-done')||{}).innerText || '',
        canSkip: !!document.querySelector('#wiz')
    })""")
    if "실패" in s["list"] and "실패" in s["done"]:
        ok("D4", "진단자-조회", "조회 실패 시 원인 안내 표시")
    else:
        F("D4", "P2", "진단자-조회", "조회 실패 안내가 불충분", s)
    if "자가진단 없이 시작" in page.inner_text("#wiz"):
        ok("D4", "진단자-조회", "조회 실패해도 진행 경로 제공")
    else:
        F("D4", "P1", "진단자-조회", "조회 실패 시 진행할 방법이 없음", "")
    page.close()

    b.close()

print("\n" + "="*66)
print(f"발견 {len(findings)}건")
for s in ["P0","P1","P2","P3"]:
    n = [f for f in findings if f["sev"] == s]
    if n:
        print(f"  {s}: {len(n)}건")
print(json.dumps(findings, ensure_ascii=False, indent=1))
