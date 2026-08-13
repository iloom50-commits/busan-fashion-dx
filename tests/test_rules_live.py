"""배포된 사이트에서 Firestore 보안규칙이 실제로 걸리는지 검증한다.

규칙을 Firebase 콘솔에서 게시한 뒤 실행한다.
게시 전에 실행하면 수정·삭제·생성이 통과하므로 FAIL이 나온다 (정상 동작).

────────────────────────────────────────────────────────────────────────
[안전 설계] 이 테스트는 실제 데이터를 파괴하지 않는다.

  2026-08-13, 이 테스트의 초기 버전이 실제 진단 기록(그린섬유)을 삭제한 사고가
  있었다. 규칙 게시 전에 실행했더니 삭제가 실제로 성공했기 때문이다.
  백업에서 복구했으나, 같은 사고가 반복되지 않도록 아래 원칙을 지킨다.

  · 수정·삭제는 '이 테스트가 방금 만든 문서'만 대상으로 한다. 실제 기록은 읽기만 한다.
  · 형식 미달 생성이 성공하면 만들어진 문서를 즉시 지운다.

[남는 흔적] 규칙이 게시된 뒤에는 삭제가 막히므로, 테스트가 만든 문서 1건이
  남는다. 문서 ID를 출력하니 Firebase 콘솔에서 지울 것.
  (존재하지 않는 문서를 삭제 대상으로 삼는 방법도 시도했으나, 규칙과 무관하게
   DENIED가 반환되어 거짓 통과했다. 그래서 실제 문서를 만들어 검사한다.)
────────────────────────────────────────────────────────────────────────
"""
import sys, io
from playwright.sync_api import sync_playwright
from helpers import Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LIVE = "https://dx-diagnostic-tool.vercel.app"
KEEP_ID = "Dxk2iWqtUURAlXlVc76A"      # 그린섬유 — 실제 진단 기록. 읽기만 한다
KEEP_COMPANY = "그린섬유"
PROBE_COMPANY = "[규칙검증] 삭제해주세요"   # 테스트가 만드는 문서

r = Results()

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    page.goto(f"{LIVE}/expert.html", wait_until="networkidle")
    page.wait_for_function("typeof firebase !== 'undefined'")

    out = page.evaluate("""async ([keepId, probeCompany]) => {
        const db = firebase.firestore();
        const res = { strayIds: [] };

        // 기준 문서 존재 확인 — 없으면 나머지를 건너뛴다
        const before = await db.collection('diagnoses').doc(keepId).get();
        if (!before.exists) return {abort: '기준 문서가 없다: ' + keepId};

        try { const s = await db.collection('diagnoses').get(); res.read = 'OK:' + s.size; }
        catch(e) { res.read = 'DENIED'; }

        // 검사용 문서를 하나 만든다. 규칙에 맞는 정상 형식이어야 생성된다.
        let probe = null;
        try {
            probe = await db.collection('diagnoses').add({
                type: 'self',
                timestamp: firebase.firestore.FieldValue.serverTimestamp(),
                company: probeCompany,
                track: 'A',
                scores: {work:1, process:1, quality:1, material:1, basic:1, leader:1}
            });
            res.validCreate = 'OK';
        } catch(e) { res.validCreate = 'DENIED'; }

        if (probe) {
            // 수정·삭제는 이 문서만 대상으로 한다
            try { await db.collection('diagnoses').doc(probe.id).update({company: '수정됨'}); res.update = 'OK'; }
            catch(e) { res.update = 'DENIED'; }

            try { await db.collection('diagnoses').doc(probe.id).delete(); res.del = 'OK'; }
            catch(e) { res.del = 'DENIED'; res.strayIds.push(probe.id); }
        } else {
            res.update = 'N/A'; res.del = 'N/A';
        }

        // 형식 미달 생성: 성공하면 즉시 지운다
        try {
            const ref = await db.collection('diagnoses').add({junk: 'x'});
            res.badCreate = 'OK';
            try { await ref.delete(); } catch(e2) { res.strayIds.push(ref.id); }
        } catch(e) { res.badCreate = 'DENIED'; }

        try {
            const ref = await db.collection('secrets').add({a: 1});
            res.otherPath = 'OK';
            try { await ref.delete(); } catch(e2) {}
        } catch(e) { res.otherPath = 'DENIED'; }

        const after = await db.collection('diagnoses').doc(keepId).get();
        res.keepAlive = after.exists ? after.data().company : '(사라짐)';
        res.keepScore = after.exists ? after.data().totalScore : null;
        return res;
    }""", [KEEP_ID, PROBE_COMPANY])
    b.close()

if out.get("abort"):
    print(f"  중단: {out['abort']}")
    print("  백업에서 복구한 뒤 다시 실행할 것: C:\\tmp\\busan-dx-firestore-backup-2026-08-13.json")
    sys.exit(1)

r.check("읽기 허용 (의도된 동작)", out["read"].startswith("OK"), out["read"])
r.check("정상 형식 생성 허용", out["validCreate"] == "OK", out["validCreate"])
r.check("수정 차단", out["update"] == "DENIED", out["update"])
r.check("삭제 차단", out["del"] == "DENIED", out["del"])
r.check("형식 미달 생성 차단", out["badCreate"] == "DENIED", out["badCreate"])
r.check("다른 경로 접근 차단", out["otherPath"] == "DENIED", out["otherPath"])
r.check(f"{KEEP_COMPANY} 기록 보존", out["keepAlive"] == KEEP_COMPANY, out["keepAlive"])
r.check(f"{KEEP_COMPANY} 점수 보존", out["keepScore"] == 18, str(out["keepScore"]))

if out.get("strayIds"):
    print(f"\n  ⚠ 테스트가 만든 문서가 남았습니다 (삭제가 차단되어 정상):")
    for sid in out["strayIds"]:
        print(f"     {sid}")
    print("     Firebase 콘솔 > Firestore > diagnoses 에서 삭제해 주세요.")

sys.exit(r.summary())
