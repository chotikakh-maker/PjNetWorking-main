"""
main.py
-------
Entry point ของ server เปิดสองอย่างพร้อมกัน:
1. HTTP server (static file server) สำหรับ serve หน้าเว็บใน client/
2. WebSocket server สำหรับสื่อสาร real-time ระหว่าง server กับผู้เล่นแต่ละคน

วิธีรัน: py server/main.py (รันจาก root ของโปรเจกต์ ไม่ใช่จากในโฟลเดอร์ server/)
"""

import asyncio
import functools
import http.server
import os
import socket
import threading

from server import config
from server.network.ws_server import run_server

CLIENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client")


def get_local_ip():
    """
    หา IP ของเครื่องนี้ในวง LAN (ไม่ใช่ 127.0.0.1) เพื่อบอกให้เพื่อนต่อผ่าน IP นี้
    วิธีนี้ไม่ได้เชื่อมต่อจริง แค่ใช้ trick ของ socket เพื่อดูว่า OS จะเลือก network interface ไหน
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_http_server():
    """
    รัน static file server ใน thread แยกต่างหาก (แยกจาก asyncio event loop ของ websocket)
    เพราะ http.server เป็นแบบ blocking (synchronous) ธรรมดา ไม่ได้เขียนด้วย async
    """
    handler_class = functools.partial(http.server.SimpleHTTPRequestHandler, directory=CLIENT_DIR)
    httpd = http.server.ThreadingHTTPServer((config.HOST, config.HTTP_PORT), handler_class)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    local_ip = get_local_ip()

    start_http_server()

    print("=" * 50)
    print("ป๊อกเด้ง (Pok Deng) Multiplayer Server เริ่มทำงานแล้ว")
    print("=" * 50)
    print(f"เปิดเล่นบนเครื่องนี้:      http://localhost:{config.HTTP_PORT}")
    print(f"ให้เพื่อนในวง LAN เข้าเล่น: http://{local_ip}:{config.HTTP_PORT}")
    print("=" * 50)

    # asyncio.run เปิด event loop แล้วรัน run_server (async function) จนกว่าจะถูก Ctrl+C
    try:
        asyncio.run(run_server(config.HOST, config.WS_PORT))
    except KeyboardInterrupt:
        print("\nปิด server แล้ว")


if __name__ == "__main__":
    main()
