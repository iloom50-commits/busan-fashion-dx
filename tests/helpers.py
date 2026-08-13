"""브라우저 검증 공통 헬퍼.

프로덕션 Firestore를 오염시키지 않도록 collection().add()를 가로채
payload만 window.__writes에 모은다. 조회도 가짜 문서를 반환한다.

서버 기동:
    python -m http.server 8899 --directory <저장소>/v2
"""

BASE = "http://localhost:8899"

PATCH = """(fakes) => {
    const inst = firebase.firestore();
    window.__writes = [];
    inst.collection = (name) => ({
        add: async (data) => { window.__writes.push({collection:name, data}); return {id:'faked'}; },
        where: () => ({ get: async () => ({ docs: fakes.map(f => ({ id: f.id, data: () => f })) }) }),
        orderBy: () => ({ get: async () => ({ docs: [] }) })
    });
}"""

# 개인정보를 저장하지 않기로 했으므로 자가진단 기록에도 ceo/phone/email이 없다
FAKE_SELF = {
    "id": "selfdoc1", "type": "self", "company": "테스트봉제",
    "bizNum": "1234567890", "emp": "5~9명", "bizType": "임가공(수주)", "track": "B",
    "gradeLv": 2, "gradeTxt": "LV2. 도입", "totalScore": 13,
    "scores": {"work": 1, "process": 3, "quality": 1, "material": 3, "basic": 1, "leader": 5},
}


def expert_login(page, code="2026"):
    """진단자 로그인 게이트를 통과한다."""
    page.fill("#pw-input", code)
    page.click("#auth-screen >> text=확인")
    page.wait_for_selector("text=자가진단 결과 불러오기")


def fill_self_form(page, comp="테스트봉제", ceo="홍길동",
                   biz="123-45-67890", phone="010-1111-2222"):
    """자가진단 기업정보 화면을 채우고 다음으로 넘어간다."""
    page.fill("#si-comp", comp)
    page.fill("#si-ceo", ceo)
    page.fill("#si-biznum", biz)
    page.fill("#si-phone", phone)
    page.click("div.seg-card:has-text('5~9명')")
    page.click("div.seg-card:has-text('임가공(수주)')")
    page.click("text=다음 →")


def complete_self_diag(page):
    """Track 선택 후 6개 영역을 채우고 결과 화면까지 진행한다."""
    page.click("div:has-text('Track B') >> nth=-1")
    page.wait_for_selector("text=6개 영역 자가진단")
    for aid, idx in [("work", 0), ("process", 1), ("quality", 0),
                     ("material", 1), ("basic", 0), ("leader", 2)]:
        page.click(f"button[onclick=\"setSelfScore('{aid}',{idx})\"]")
    page.click("text=결과 보기 →")
    page.wait_for_selector("text=자가진단 완료")


class Results:
    """테스트 결과 수집기."""

    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        detail = str(detail) if detail else ""
        self.rows.append((name, ok, detail))
        print(("  PASS  " if ok else "  FAIL  ") + name + ((" -- " + detail) if detail else ""))

    def summary(self):
        fails = [r for r in self.rows if not r[1]]
        print(f"\n총 {len(self.rows)}건 중 통과 {len(self.rows)-len(fails)}건, 실패 {len(fails)}건")
        for n, _, d in fails:
            print(f"  FAILED: {n} :: {d}")
        return 1 if fails else 0
