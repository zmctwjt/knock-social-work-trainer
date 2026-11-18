"""移动端适配验收：390px 宽度下检查横向溢出与关键元素可见性。"""
import shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(r'F:\毕业设计\work')))
from ui_smoke import CDP, CHROME, PORT, PROFILE, SHOTS, http_json, launch_chrome, open_page

BASE = "http://127.0.0.1:8000"
FAILS = []

def check(cdp, label, selector=None):
    # 页面是否横向溢出：scrollWidth 超过 clientWidth 太多即为溢出
    overflow = cdp.eval(
        "(() => { const d=document.documentElement;"
        "return d.scrollWidth - d.clientWidth; })()"
    )
    ok = (overflow or 0) <= 2
    if not ok:
        FAILS.append(f"{label}: 横向溢出 {overflow}px")
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:28s} 横向溢出={overflow}px")
    return ok

def main():
    proc = launch_chrome(window_size="390,844")
    try:
        cdp = open_page(BASE, window_size="390,844")

        time.sleep(4)

        print("\n=== 学生端（未登录）===")
        check(cdp, "首页")
        cdp.shot(SHOTS / "m_home.png")

        print("\n=== 教师端 ===")
        cdp.eval("localStorage.clear()")
        cdp.eval(f"location.href='{BASE}/#/login'"); time.sleep(4)
        cdp.eval("""(()=>{const r=[...document.querySelectorAll('.acc-row')].find(b=>b.textContent.includes('teacher01'));r&&r.click()})()""")
        time.sleep(0.8)
        cdp.eval("document.querySelector('button.login-submit.btn-primary').click()")
        time.sleep(7)
        check(cdp, "教师-班级总览")
        cdp.shot(SHOTS / "m_teacher.png")
        for tab in ["训练趋势", "学员画像"]:
            cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='%s');b&&b.click()})()""" % tab)
            time.sleep(3)
            check(cdp, f"教师-{tab}")

        print("\n=== 管理端 ===")
        cdp.eval("localStorage.clear()")
        cdp.eval(f"location.href='{BASE}/#/login'"); time.sleep(4)
        cdp.eval("""(()=>{const r=[...document.querySelectorAll('.acc-row')].find(b=>b.textContent.includes('admin01'));r&&r.click()})()""")
        time.sleep(0.8)
        cdp.eval("document.querySelector('button.login-submit.btn-primary').click()")
        time.sleep(7)
        check(cdp, "管理-运行概览")
        cdp.shot(SHOTS / "m_admin.png")
        for tab in ["账号管理", "平台趋势"]:
            cdp.eval("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='%s');b&&b.click()})()""" % tab)
            time.sleep(3)
            check(cdp, f"管理-{tab}")
        cdp.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 处横向溢出：")
        for f in FAILS: print("   -", f)
        return 1
    print("✅ 移动端（390px）无横向溢出")
    return 0

if __name__ == "__main__":
    sys.exit(main())
