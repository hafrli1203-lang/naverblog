"""
main.py — 하위 호환 래퍼
이전 배포에서 `main:app`으로 시작하던 설정을 유지하면서
실제 로직은 backend.app 에 위임합니다.
"""
import sys
import os

# Windows cp949 콘솔에서 유니코드 출력 에러 방지
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass

# backend 패키지를 임포트할 수 있도록 상위 디렉토리를 sys.path에 추가
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import app  # noqa: F401 — gunicorn이 main:app 을 사용

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port)
