"""자가진단 첫 단계 — 개인정보 수집·이용/제공 동의 화면을 검증한다.

원문: 부산테크노파크 「개인정보 수집·이용 / 제공 동의서」(개인정보동의.hwp) 를 그대로 보여준다.
동의하지 않으면 다음 단계로 갈 수 없고, 동의 여부·일시는 진단 기록에 함께 저장한다.
"""
import sys, io
from datetime import datetime
from playwright.sync_api import sync_playwright
from helpers import BASE, PATCH, FAKE_SELF, fill_self_form, complete_self_diag, Results

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 원문에서 빠지면 안 되는 문장 (hwp 본문 추출 결과에서 그대로 가져왔다)
ORIGINAL = [
    "개인정보 수집·이용 / 제공 동의서",
    "개인정보 보호법 제15조, 제17조, 제24조",
    "신발패션진흥단 섬유패션센터",
    "사업 신청 자격 검토 등의 원활한 사업 수행",
    "지원사업 안내 및 자료발송 등 사업홍보",
    "회사명, 대표자명, 주소, 전화번호, 사업자등록번호",
    "성명, 소속/지위, 휴대폰, 전화, 팩스, e-mail",
    "신청일로부터 이용목적 달성 시 까지",
    "신청자는 개인정보 수집 동의에 거부할 권리가 있습니다",
    "본인은 (재)부산테크노파크가 사업참여 목적으로 본인의 개인정보를 수집·이용 및 제공하는 것에 동의합니다.",
]

r = Results()
alerts = []

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda d: (alerts.append(d.message), d.accept()))

    page.goto(f"{BASE}/index.html")
    page.wait_for_function("typeof firebase !== 'undefined' && typeof render === 'function'")
    page.evaluate(PATCH, [FAKE_SELF])

    # ===== 첫 화면이 동의 화면이다 =====
    print("\n=== 첫 화면 ===")
    page.wait_for_selector("#consent-agree")
    wiz = page.inner_text("#wiz")
    for s in ORIGINAL:
        r.check(f"원문 포함: {s[:24]}", s in wiz)
    r.check("기업정보 입력칸은 아직 없음", page.query_selector("#si-comp") is None)
    labels = page.eval_on_selector_all(".stepper-label", "els => els.map(e => e.innerText)")
    r.check("진행 표시줄 첫 단계가 개인정보동의", labels[:1] == ["개인정보동의"], str(labels))
    r.check("진행 표시줄 5단계", len(labels) == 5, str(labels))

    # ===== 선택 없이 다음 → 막힘 =====
    print("\n=== 선택 없이 다음 ===")
    alerts.clear()
    page.click("text=다음 →")
    page.wait_for_timeout(200)
    r.check("선택 없이 다음 시 안내창", len(alerts) == 1, str(alerts))
    r.check("선택 없이 다음 시 그대로 머묾", page.query_selector("#si-comp") is None)

    # ===== 동의하지 않음 → 막힘 =====
    print("\n=== 동의하지 않음 ===")
    page.click("#consent-disagree")
    alerts.clear()
    page.click("text=다음 →")
    page.wait_for_timeout(200)
    r.check("미동의 시 그대로 머묾", page.query_selector("#si-comp") is None)
    r.check("미동의 시 참여 불가 안내 표시",
            "동의하지 않으시면" in page.inner_text("#wiz") or any("동의" in a for a in alerts),
            str(alerts))

    # ===== 동의함 → 기업정보로 =====
    print("\n=== 동의함 ===")
    page.click("#consent-agree")
    page.click("text=다음 →")
    page.wait_for_selector("#si-comp", timeout=3000)
    r.check("동의 후 기업정보 화면", page.query_selector("#si-comp") is not None)

    # ===== 이전으로 돌아가도 동의 선택 유지 =====
    print("\n=== 이전 ===")
    page.evaluate("prev()")
    page.wait_for_selector("#consent-agree")
    r.check("이전 시 동의 선택 유지",
            "selected" in (page.get_attribute("#consent-agree", "class") or ""))
    page.click("text=다음 →")
    page.wait_for_selector("#si-comp")

    # ===== 저장 기록에 동의 여부·일시 =====
    print("\n=== 저장 기록 ===")
    fill_self_form(page)
    complete_self_diag(page)
    page.wait_for_function("window.__writes && window.__writes.length > 0", timeout=8000)
    data = page.evaluate("window.__writes[0].data")
    r.check("저장에 consentAgreed=true", data.get("consentAgreed") is True, str(data.get("consentAgreed")))
    at = data.get("consentAt")
    try:
        ok = isinstance(at, str) and datetime.fromisoformat(at.replace("Z", "+00:00")).year >= 2026
    except ValueError:
        ok = False
    r.check("저장에 consentAt(ISO 일시)", ok, str(at))
    r.check("저장 필드 25개 이하(보안규칙)", len(data) <= 25, str(len(data)))
    for k in ["ceo", "phone", "email"]:
        r.check(f"저장에 {k} 없음", k not in data)

    # ===== 처음부터 다시 → 동의를 다시 받는다 =====
    print("\n=== 다시 시작 ===")
    page.evaluate("restart()")
    page.wait_for_selector("#consent-agree")
    r.check("다시 시작 시 동의 화면",
            "selected" not in (page.get_attribute("#consent-agree", "class") or ""))

    # ===== 모바일 폭에서도 버튼이 화면 안에 있다 =====
    print("\n=== 모바일 ===")
    m = b.new_page(viewport={"width": 375, "height": 812})
    m.goto(f"{BASE}/index.html")
    m.wait_for_selector("#consent-agree")
    box = m.locator("text=다음 →").bounding_box()
    r.check("모바일에서 다음 버튼이 가로 폭 안", box is not None and box["x"] + box["width"] <= 375, str(box))
    sw = m.evaluate("document.documentElement.scrollWidth")
    r.check("모바일 가로 스크롤 없음", sw <= 375, str(sw))

    b.close()

sys.exit(r.summary())
