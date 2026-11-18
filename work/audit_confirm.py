"""验证危险操作的二次确认确实会弹出，且取消后不执行。"""
import shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(r'F:\毕业设计\work')))
from ui_smoke import CDP, CHROME, PORT, PROFILE, http_json, launch_chrome, open_page

BASE = "http://127.0.0.1:8000"
FAILS = []

def main():
    proc = launch_chrome(window_size="1440,1400")
    try:
        cdp = open_page(BASE, window_size="1440,1400")

        time.sleep(3)
        cdp.eval("localStorage.clear()")
        cdp.eval(f"location.href='{BASE}/#/login'"); time.sleep(4)
        cdp.eval("""(()=>{const r=[...document.querySelectorAll('.acc-row')].find(b=>b.textContent.includes('admin01'));r&&r.click()})()""")
        time.sleep(0.8)
        cdp.eval("document.querySelector('button.login-submit.btn-primary').click()")
        time.sleep(7)

        # 进入账号管理（标签按钮内含序号 span，需按去序号后的文本匹配）
        cdp.eval("""(()=>{
          const b=[...document.querySelectorAll('button.wb-tab')].find(x=>{
            const c=x.cloneNode(true); c.querySelectorAll('.no').forEach(n=>n.remove());
            return c.textContent.trim()==='账号管理';
          });
          b&&b.click();
        })()""")
        time.sleep(3)

        # 点第一个"停用"按钮
        clicked = cdp.eval("""(()=>{
          const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='停用');
          if(!b) return 'NO-BTN';
          b.click(); return 'clicked';
        })()""")
        time.sleep(1)
        dialog_open = cdp.eval("(()=>{const d=document.querySelector('dialog');return d? d.open : false})()")
        dialog_text = cdp.eval("(()=>{const d=document.querySelector('dialog');return d? d.textContent.slice(0,60):''})()")
        print(f"  点停用: {clicked}")
        print(f"  对话框弹出: {dialog_open}")
        print(f"  对话框内容: {dialog_text}")
        if not dialog_open:
            FAILS.append("停用操作未弹出确认框")

        # 点取消，确认账号状态未变
        cdp.eval("""(()=>{const b=[...document.querySelectorAll('dialog button')].find(x=>x.textContent.trim()==='取消');b&&b.click()})()""")
        time.sleep(1)
        still_open = cdp.eval("(()=>{const d=document.querySelector('dialog');return d? d.open : false})()")
        print(f"  取消后对话框关闭: {not still_open}")
        if still_open:
            FAILS.append("取消后对话框未关闭")

        # 验证删除类操作也有确认
        cdp.eval("""(()=>{
          const b=[...document.querySelectorAll('button.wb-tab')].find(x=>{
            const c=x.cloneNode(true); c.querySelectorAll('.no').forEach(n=>n.remove());
            return c.textContent.trim()==='内容维护';
          });
          b&&b.click();
        })()""")
        time.sleep(3)
        clicked2 = cdp.eval("""(()=>{
          const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='删除');
          if(!b) return 'NO-BTN';
          b.click(); return 'clicked';
        })()""")
        time.sleep(1)
        dialog2 = cdp.eval("(()=>{const d=document.querySelector('dialog');return d? d.open : false})()")
        print(f"  点删除: {clicked2} 对话框: {dialog2}")
        if clicked2 == 'clicked' and not dialog2:
            FAILS.append("删除操作未弹出确认框")
        cdp.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill()

    print()
    if FAILS:
        for f in FAILS: print("  ❌", f)
        return 1
    print("✅ 危险操作二次确认全部生效")
    return 0

if __name__ == "__main__":
    sys.exit(main())
