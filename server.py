import os
import json
import hashlib
from io import BytesIO
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from PIL import Image

import matcher

PORT = 7860
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "rename_history.json")

def scan_and_match(folder_path: str, txt_content: str):
    """TXT 프롬프트와 폴더 이미지를 매칭. 결과 구성(묶음/누락/파일명)은 프론트에서 처리."""
    if not os.path.isdir(folder_path):
        return {"error": f"폴더가 존재하지 않습니다: {folder_path}"}

    prompts = matcher.parse_txt_prompts(txt_content)
    if not prompts:
        return {"error": "TXT 파일에서 유효한 프롬프트 번호 항목을 찾을 수 없습니다."}

    if not any(f.lower().endswith(matcher.VALID_EXTS) for f in os.listdir(folder_path)):
        return {"error": "지정한 폴더에 이미지 파일(.jpeg, .jpg, .png, .webp)이 없습니다."}

    for p, scene in zip(prompts, matcher.extract_scene_texts([p["prompt"] for p in prompts])):
        p["scene"] = scene
    result = matcher.match(folder_path, prompts)
    return {"folder_path": folder_path, "prompts": prompts, **result}


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            
            # 썸네일 스트리밍
            if parsed.path == "/api/thumbnail":
                params = parse_qs(parsed.query)
                file_path = params.get("path", [None])[0]
                if file_path and os.path.exists(file_path):
                    try:
                        with Image.open(file_path) as img:
                            img.thumbnail((320, 320))
                            bio = BytesIO()
                            rgb_img = img.convert("RGB")
                            rgb_img.save(bio, format="JPEG", quality=80)
                            bio.seek(0)
                            
                            self.send_response(200)
                            self.send_header("Content-Type", "image/jpeg")
                            self.send_header("Cache-Control", "max-age=3600")
                            self.end_headers()
                            self.wfile.write(bio.read())
                            return
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                        return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return

            return super().do_GET()
        except Exception as e:
            print(f"[GET 에러] {e}")

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8", errors="ignore")
            
            try:
                req_json = json.loads(post_data) if post_data else {}
            except Exception:
                req_json = {}

            # 0. TXT 파일 경로 직접 읽기 API
            if parsed.path == "/api/read_txt":
                file_path = req_json.get("file_path", "").strip().replace('"', '')
                if file_path and os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            txt_data = f.read()
                        self._send_json({"success": True, "content": txt_data, "filename": os.path.basename(file_path)})
                        return
                    except Exception as e:
                        self._send_json({"error": f"파일 읽기 오류: {e}"}, status=500)
                        return
                else:
                    self._send_json({"error": "지정한 TXT 파일을 찾을 수 없습니다."}, status=404)
                    return

            # 1. 자동 스캔 및 매칭 분석 API
            if parsed.path == "/api/scan":
                folder_path = req_json.get("folder_path", "").strip()
                txt_content = req_json.get("txt_content", "").strip()

                if not folder_path or not txt_content:
                    self._send_json({"error": "폴더 경로와 TXT 내용을 모두 제공해야 합니다."}, status=400)
                    return

                result = scan_and_match(folder_path, txt_content)
                self._send_json(result)
                return

            # 2. 파일명 일괄 변경 실행 API
            if parsed.path == "/api/rename":
                folder_path = req_json.get("folder_path", "").strip()
                rename_plan = req_json.get("rename_plan", [])

                if not os.path.exists(folder_path):
                    self._send_json({"error": "폴더가 존재하지 않습니다."}, status=400)
                    return

                history = []
                renamed_success = []
                errors = []

                temp_mappings = []
                for item in rename_plan:
                    old_name = item.get("old_name")
                    new_name = item.get("new_name")
                    if not old_name or not new_name or old_name == new_name:
                        continue

                    old_full = os.path.join(folder_path, old_name)
                    new_full = os.path.join(folder_path, new_name)

                    if os.path.exists(old_full):
                        temp_name = f"__tmp_sort_{hashlib.md5(old_name.encode()).hexdigest()[:8]}_{old_name}"
                        temp_full = os.path.join(folder_path, temp_name)
                        try:
                            os.rename(old_full, temp_full)
                            temp_mappings.append((temp_full, new_full, old_name, new_name))
                        except Exception as e:
                            errors.append(f"{old_name} 임시 변경 실패: {e}")

                for temp_full, new_full, old_name, new_name in temp_mappings:
                    try:
                        if os.path.exists(new_full):
                            base, ext = os.path.splitext(new_full)
                            new_full = f"{base}_dup{ext}"
                            new_name = os.path.basename(new_full)
                        
                        os.rename(temp_full, new_full)
                        renamed_success.append({"from": old_name, "to": new_name})
                        history.append({"from": new_name, "to": old_name})
                    except Exception as e:
                        try:
                            os.rename(temp_full, os.path.join(folder_path, old_name))
                        except Exception:
                            pass
                        errors.append(f"{old_name} -> {new_name} 변경 실패: {e}")

                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump({"folder_path": folder_path, "history": history}, f, ensure_ascii=False, indent=2)

                self._send_json({
                    "success": True,
                    "renamed_count": len(renamed_success),
                    "errors": errors,
                    "renamed_items": renamed_success
                })
                return

            # 3. 되돌리기 (Undo) API
            if parsed.path == "/api/undo":
                if not os.path.exists(HISTORY_FILE):
                    self._send_json({"error": "되돌릴 수 있는 이전 변경 내역이 없습니다."}, status=400)
                    return

                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                folder_path = saved.get("folder_path")
                history = saved.get("history", [])

                reverted = []
                undo_errors = []

                for h in history:
                    curr_name = h["from"]
                    orig_name = h["to"]
                    curr_full = os.path.join(folder_path, curr_name)
                    orig_full = os.path.join(folder_path, orig_name)

                    if os.path.exists(curr_full):
                        try:
                            os.rename(curr_full, orig_full)
                            reverted.append({"from": curr_name, "to": orig_name})
                        except Exception as e:
                            undo_errors.append(f"{curr_name} 복구 실패: {e}")

                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)

                self._send_json({
                    "success": True,
                    "reverted_count": len(reverted),
                    "errors": undo_errors
                })
                return

            self.send_response(404)
            self.end_headers()
        except Exception as e:
            print(f"[POST 에러] {e}")
            try:
                self._send_json({"error": f"서버 내부 오류: {e}"}, status=500)
            except Exception:
                pass

    def _send_json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

def run():
    import webbrowser
    import socket
    import threading

    # 윈도우의 SO_REUSEADDR는 이미 사용 중인 포트에도 중복 바인딩을 허용해서
    # 옛 서버가 켜져 있으면 요청이 그쪽으로 가버림 → 윈도우에선 끄고 다음 포트로 넘어가게 함
    ThreadingHTTPServer.allow_reuse_address = os.name != "nt"
    port = PORT
    httpd = None

    # 포트 사용 중이면 다음 포트 탐색
    for p in range(PORT, PORT + 20):
        try:
            httpd = ThreadingHTTPServer(("", p), RequestHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print("사용 가능한 포트를 찾을 수 없습니다.")
        return

    url = f"http://localhost:{port}"
    print("=" * 55)
    print(" [스마트 이미지 정렬기]")
    print(f" 서버가 정상 시작되었습니다: {url}")
    print(" 브라우저가 잠시 후 자동으로 열립니다.")
    print(" (종료하려면 이 창에서 Ctrl + C 를 누르세요)")
    print("=" * 55)

    # 1초 뒤 브라우저 자동 오픈
    def open_browser():
        webbrowser.open(url)

    threading.Timer(1.0, open_browser).start()

    # CLIP 모델 미리 로드 (첫 분석 대기 시간 단축, 최초 1회 약 1.7GB 다운로드)
    def preload():
        print(" CLIP 모델 로딩 중...")
        matcher.load_model()
        print(" CLIP 모델 준비 완료")
    threading.Thread(target=preload, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
        httpd.server_close()

if __name__ == "__main__":
    run()
