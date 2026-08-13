"""배포된 사이트에서 Firestore 보안규칙이 실제로 걸리는지 검증한다.

규칙을 Firebase 콘솔에서 게시한 뒤에 실행할 것.
게시 전에 실행하면 수정·삭제가 통과하므로 FAIL이 나온다 (정상).

읽기 전용이 아니다 — 수정·삭제를 실제로 시도한다.
KEEP_ID 문서가 살아남는지 마지막에 반드시 확인한다.
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LIVE = "https://dx-diagnostic-tool.vercel.app"
KEEP_ID = "Dxk2iWqtUURAlXlVc76A"      # 그린섬유 — 실제 진단 기록. 절대 지워지면 안 된다
KEEP_COMPANY = "그린섬유"

r = Results()

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof firebase !== 'undefined'")

    out = page.evaluate("""async ([keepId, keepCompany]) => {
        const db = firebase.firestore();
        const res = {};

        try { const s = await db.collection('diagnoses').get(); res.read = 'OK:' + s.size; }
        catch(e) { res.read = 'DENIED'; }

        // 수정 시도 — 원래 값으로 되돌릴 필요가 없도록 같은 값을 쓴다
        try { await db.collection('diagnoses').doc(keepId).update({company: keepCompany}); res.update = 'OK'; }
        catch(e) { res.update = 'DENIED'; }

        try { await db.collection('diagnoses').doc(keepId).delete(); res.del = 'OK'; }
        catch(e) { res.del = 'DENIED'; }

        try { await db.collection('diagnoses').add({junk: 'x'}); res.badCreate = 'OK'; }
        catch(e) { res.badCreate = 'DENIED'; }

        try { await db.collection('secrets').add({a: 1}); res.otherPath = 'OK'; }
        catch(e) { res.otherPath = 'DENIED'; }

        const snap = await db.collection('diagnoses').doc(keepId).get();
        res.keepAlive = snap.exists ? snap.data().company : '(사라짐)';
        return res;
    }""", [KEEP_ID, KEEP_COMPANY])
    b.close()

r.check("읽기 허용 (의도된 동작)", out["read"].startswith("OK"), out["read"])
r.check("수정 차단", out["update"] == "DENIED", out["update"])
r.check("삭제 차단", out["del"] == "DENIED", out["del"])
r.check("형식 미달 생성 차단", out["badCreate"] == "DENIED", out["badCreate"])
r.check("다른 경로 접근 차단", out["otherPath"] == "DENIED", out["otherPath"])
r.check(f"{KEEP_COMPANY} 기록 보존", out["keepAlive"] == KEEP_COMPANY, out["keepAlive"])

sys.exit(r.summary())
