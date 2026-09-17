"""
실행기: 전용 가상환경을 (최초 1회) 만들고 패키지를 설치한 뒤 server.py 실행.
표준 라이브러리만 사용하므로 시스템 파이썬으로 바로 실행 가능.

가상환경은 프로젝트 폴더가 아닌 짧은 경로(%LOCALAPPDATA%\\image-sorter\\venv)에 둔다.
torch 설치 경로가 매우 깊어서 프로젝트 폴더 안에 두면 윈도우 260자 경로 제한에 걸리기 때문.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import venv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(BASE_DIR, "requirements.txt")
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

if os.name == "nt":
    APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "image-sorter")
    VENV_PY = os.path.join(APP_DIR, "venv", "Scripts", "python.exe")
else:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".image-sorter")
    VENV_PY = os.path.join(APP_DIR, "venv", "bin", "python")
VENV_DIR = os.path.join(APP_DIR, "venv")
MARKER = os.path.join(APP_DIR, "installed.txt")


def requirements_hash() -> str:
    with open(REQUIREMENTS, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def is_installed() -> bool:
    if not (os.path.exists(VENV_PY) and os.path.exists(MARKER)):
        return False
    with open(MARKER, encoding="utf-8") as f:
        return f.read().strip() == requirements_hash()


def pip(*args):
    subprocess.check_call([VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", *args])


def install():
    print("[최초 1회] 실행 환경을 설치합니다. 인터넷 속도에 따라 몇 분 걸릴 수 있어요...")
    print(f"  설치 위치: {VENV_DIR}\n")
    os.makedirs(APP_DIR, exist_ok=True)
    try:
        if not os.path.exists(VENV_PY):
            venv.create(VENV_DIR, with_pip=True)
        # torch는 CPU 버전 (GPU 버전보다 용량이 훨씬 작고, 이미지 수십 장 분석엔 충분)
        pip("torch", "--index-url", TORCH_CPU_INDEX)
        pip("-r", REQUIREMENTS)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"\n[오류] 패키지 설치에 실패했습니다: {e}")
        print("인터넷 연결을 확인하고 다시 실행해 주세요.")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        return False
    with open(MARKER, "w", encoding="utf-8") as f:
        f.write(requirements_hash())
    print("\n설치 완료!\n")
    return True


def main():
    if sys.version_info < (3, 10):
        print(f"[오류] Python 3.10 이상이 필요합니다. (현재 {sys.version.split()[0]})")
        return 1
    if not is_installed() and not install():
        return 1
    try:
        return subprocess.call([VENV_PY, os.path.join(BASE_DIR, "server.py")], cwd=BASE_DIR)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
