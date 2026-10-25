"""Desktop entry point: monitoring exists only while this window is running it."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from app_controller import MonitorController
from windows_job import SingleInstance, WindowsJob

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / '.local'
TITLE = 'ICPPLUS Monitor'


def launch_check():
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return WindowsJob([powershell, '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                       '-File', ROOT / 'local_runner.ps1', '-QuarterHour', '-FromApp'], ROOT,
                      hidden_console=True)


class MonitorApp:
    def __init__(self, window):
        self.window = window
        self.controller = MonitorController(launch_check)
        self.closing = False
        self.last_status_mtime = None
        self.started_at = None
        window.title(TITLE)
        window.geometry('640x440')
        window.minsize(600, 430)
        window.configure(background='#f4f5f7')
        window.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#f4f5f7')
        style.configure('TLabel', background='#f4f5f7', foreground='#253247', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
        style.configure('State.TLabel', font=('Segoe UI', 15, 'bold'))
        style.configure('TButton', font=('Segoe UI', 10), padding=(16, 9))
        style.configure('Primary.TButton', background='#245da8', foreground='white')
        frame = ttk.Frame(window, padding=25)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=TITLE, style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Madrid · Toma de huellas', foreground='#64748b').pack(anchor='w', pady=(4, 22))
        self.state = tk.StringVar(value='Detenido')
        ttk.Label(frame, textvariable=self.state, style='State.TLabel').pack(anchor='w')
        self.detail = tk.StringVar(value='Pulsa Iniciar para activar las consultas.')
        ttk.Label(frame, textvariable=self.detail, wraplength=580).pack(anchor='w', pady=(6, 14))
        self.next_time = tk.StringVar(value='Próxima consulta: —')
        ttk.Label(frame, textvariable=self.next_time).pack(anchor='w')
        self.last_result = tk.StringVar(value='Última consulta: —')
        ttk.Label(frame, textvariable=self.last_result, wraplength=580).pack(anchor='w', pady=(6, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(anchor='w')
        self.start_button = ttk.Button(buttons, text='Iniciar', command=self.start, style='Primary.TButton')
        self.start_button.pack(side='left', padx=(0, 10))
        self.stop_button = ttk.Button(buttons, text='Detener', command=self.stop, state='disabled')
        self.stop_button.pack(side='left')
        links = ttk.Frame(frame)
        links.pack(anchor='w', pady=(16, 14))
        ttk.Button(links, text='Abrir panel web', command=lambda: webbrowser.open('https://ialexx-16.github.io/icpplus-monitor/')).pack(side='left', padx=(0, 10))
        ttk.Button(links, text='Ver registro', command=lambda: os.startfile(PRIVATE / 'monitor.log')).pack(side='left')
        ttk.Label(frame, text='Consultas a :00, :15, :30 y :45. La preparación comienza un minuto antes.\n'
                             'Al cerrar esta ventana se detienen las consultas y el Chrome del monitor.',
                  foreground='#64748b', wraplength=585).pack(anchor='w')
        self.refresh_result()
        self.save_state()
        self.window.after(200, self.tick)

    def save_state(self):
        PRIVATE.mkdir(exist_ok=True)
        data = {'app_pid': os.getpid(), 'running': self.controller.running,
                'check_pid': self.controller.job.pid if self.controller.job else None,
                'next_target': self.controller.target_at.isoformat() if self.controller.target_at else None,
                'updated_at': datetime.now(timezone.utc).isoformat()}
        temporary = PRIVATE / 'app-state.tmp'
        temporary.write_text(json.dumps(data), encoding='utf-8')
        temporary.replace(PRIVATE / 'app-state.json')

    def start(self):
        if not (PRIVATE / 'secrets.json').exists():
            messagebox.showerror(TITLE, 'Falta la configuración local cifrada.', parent=self.window)
            return
        self.started_at = datetime.now(timezone.utc)
        self.controller.start()
        self.render()

    def stop(self):
        self.controller.stop()
        self.render()

    def render(self):
        active = self.controller.running
        self.start_button.configure(state='disabled' if active else 'normal')
        self.stop_button.configure(state='normal' if active else 'disabled')
        if not active:
            self.state.set('Detenido')
            self.detail.set('Pulsa Iniciar para activar las consultas.')
            self.next_time.set('Próxima consulta: —')
        else:
            target = self.controller.target_at.astimezone().strftime('%H:%M:%S')
            preparation = self.controller.prepare_at.astimezone().strftime('%H:%M:%S')
            self.state.set('Preparando consulta' if self.controller.job else 'Monitor activo')
            self.detail.set('Chrome está preparando la consulta; el envío esperará al horario previsto.'
                            if self.controller.job else 'Esperando la siguiente consulta. Puedes detenerla o cerrar la aplicación.')
            self.next_time.set(f'Próxima consulta: {target} · Preparación: {preparation}')
            if self.controller.last_error:
                self.detail.set(self.controller.last_error)
        self.save_state()

    def refresh_result(self):
        try:
            path = ROOT / 'data/status.json'
            mtime = path.stat().st_mtime_ns
            if mtime == self.last_status_mtime:
                return
            data = json.loads(path.read_text(encoding='utf-8'))
            result = next(iter(data.get('profiles', {}).values()), None)
            if result:
                labels = {'unavailable': 'Sin citas', 'available': 'Posibles citas disponibles',
                          'blocked': 'Acceso rechazado por el portal', 'error': 'Error de consulta',
                          'missed': 'Horario perdido', 'requires_input': 'Faltan datos'}
                timestamp = datetime.fromisoformat(result['last_check']).astimezone().strftime('%d/%m %H:%M:%S')
                self.last_result.set(f"Última consulta: {timestamp} · {labels.get(result['status'], result['status'])}")
            self.last_status_mtime = mtime
        except (OSError, ValueError, KeyError, StopIteration):
            pass

    def tick(self):
        if self.closing:
            return
        try:
            previous = (self.controller.job, self.controller.target_at, self.controller.running)
            self.controller.tick()
            current = (self.controller.job, self.controller.target_at, self.controller.running)
            if previous != current:
                self.render()
            self.refresh_result()
        except Exception as error:
            self.controller.stop()
            self.render()
            self.detail.set('Error del monitor: ' + str(error))
        self.window.after(200, self.tick)

    def close(self):
        self.closing = True
        try:
            self.controller.stop()
            self.save_state()
        finally:
            self.window.destroy()


def main():
    # Give Windows a stable application identity instead of grouping this with IDLE.
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ICPPLUS.Monitor')
    identity = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:20]
    instance = SingleInstance('Local\\ICPPLUSMonitor-' + identity)
    window = None
    application = None
    try:
        window = tk.Tk()
        if instance.already_running:
            window.withdraw()
            messagebox.showinfo(TITLE, 'ICPPLUS Monitor ya está abierto.')
            window.destroy()
            return
        application = MonitorApp(window)
        window.mainloop()
    finally:
        if application:
            application.controller.stop()
        instance.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        PRIVATE.mkdir(exist_ok=True)
        (PRIVATE / 'app-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise
