import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

from scripts.wait_port import wait          # noqa: E402

REQUIRED = [
    ("flask", "flask", "Web 介面起不來"),
    ("fastmcp", "fastmcp", "連不到 MCP Server"),
    ("anthropic", "anthropic", "Claude 不可用"),
    ("openai", "openai", "本地 LLM 不可用、FAQ 語意檢索退層"),
    ("dotenv", "python-dotenv", ".env 整份被忽略，金鑰會變成空的"),
    ("numpy", "numpy", "FAQ 語意檢索與 optimize_plan_mix 失效"),
    ("sklearn", "scikit-learn", "FAQ 只剩關鍵字比對"),
    ("scipy", "scipy", "optimize_plan_mix 工具失效"),
]

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_PORT = 8000


def line(c="=", w=52):
    print(c * w)


def check_packages() -> bool:
    import importlib.util
    print(f"[1/4] 直譯器\n      {sys.executable}")
    missing = [(m, pip, why) for m, pip, why in REQUIRED
               if importlib.util.find_spec(m) is None]
    if not missing:
        print("      套件齊全")
        return True
    print("\n[X] 相依套件不齊，缺少：")
    for m, pip, why in missing:
        print(f"      - {pip:14} → {why}")
    print("\n    請用上面那個直譯器安裝（不要用別的 python）：\n")
    print(f'      "{sys.executable}" -m pip install -r requirements.txt\n')
    return False


def check_port_free(port: int) -> bool:
    import socket
    s_ = socket.socket()
    s_.settimeout(1)
    try:
        s_.connect(("127.0.0.1", port))
        occupied = True
    except Exception:
        occupied = False
    finally:
        s_.close()
    if not occupied:
        return True

    print(f"\n[X] {port} 埠已經有行程在聽——可能是上次沒關乾淨的 MCP Server。")
    try:
        import subprocess
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
        pids = []
        for ln in out.splitlines():
            parts = ln.split()
            if len(parts) >= 5 and "LISTENING" in ln and parts[1].endswith(f":{port}"):
                pids.append(parts[-1])
                print(f"      {parts[1]:24} PID {parts[-1]}")
        if pids:
            print("\n停止指令：")
            for pid in dict.fromkeys(pids):
                print(f"      taskkill /PID {pid} /F")
    except Exception:
        print(f"      netstat -ano | findstr :{port}")
    print()
    return False


def start_mcp_server():
    log = os.path.join(BASE, "server.log")
    print(f"[2/4] 啟動 MCP Server（背景，輸出寫到 {os.path.basename(log)}）")
    cmd = [sys.executable, "-m", "uvicorn", "mcp_server.server:app",
           "--host", "0.0.0.0", "--port", str(MCP_PORT), "--loop", "asyncio"]
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    with open(log, "w", encoding="utf-8") as f:
        return subprocess.Popen(cmd, cwd=BASE, stdout=f, stderr=subprocess.STDOUT,
                                creationflags=flags)


def lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def main():
    os.chdir(BASE)
    line()
    print("  可信賴雲 AI Agent - Web 版")
    line()
    print()

    if not check_packages():
        return 1

    if not check_port_free(MCP_PORT):
        return 1

    proc = start_mcp_server()

    print(f"[3/4] 等待 MCP Server 就緒（最多 25 秒）...")
    if not wait("127.0.0.1", MCP_PORT, 25.0):
        print(f"\n[X] MCP Server 25 秒內沒有就緒，請看 server.log。")
        print("    常見原因：8000 埠被占用，或套件版本不合。")
        proc.terminate()
        return 1
    print("      就緒")

    from config import settings
    port = settings.WEB_PORT
    ip = lan_ip()
    print("[4/4] 啟動 Web 介面\n")
    print(f"  這台電腦        http://127.0.0.1:{port}")
    print(f"  管理介面        http://127.0.0.1:{port}/admin")
    if ip:
        print(f"  同網段其他電腦  http://{ip}:{port}")
    print("  停止請按 Ctrl+C")
    line()
    print()

    try:
        subprocess.call([sys.executable, "web.py"], cwd=BASE)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nWeb 介面已結束。MCP Server 仍在背景執行，關閉它的視窗即可停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
