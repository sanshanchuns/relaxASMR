import queue
import threading
import tkinter as tk

from gui.tk_thread import _QUEUE_ATTR, bind_ui_root, ensure_ui_pump, schedule_on_main


def test_schedule_on_main_from_worker_thread() -> None:
    root = tk.Tk()
    root.withdraw()
    bind_ui_root(root)
    done: list[int] = []

    def worker() -> None:
        schedule_on_main(root, done.append, 1)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=1.0)

    q: queue.Queue = getattr(root, _QUEUE_ATTR)
    for _ in range(100):
        try:
            while True:
                q.get_nowait()()
        except queue.Empty:
            pass
        if done:
            break
        root.update()

    root.destroy()
    assert done == [1]
