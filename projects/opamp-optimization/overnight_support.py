"""Run-mode helpers. No simulator calls or permanent Windows setting changes."""
import os

def fully_passing(result):
    checks=result.get('checks',[])
    return (result.get('status')=='measured' and result.get('feasible') is True
            and bool(checks) and all(row.get('status')=='pass' for row in checks))

class SleepGuard:
    """Request system wakefulness on this worker thread; allow the screen to sleep."""
    def __init__(self,enabled=True):
        self.enabled=enabled;self.active=False
    def acquire(self):
        if not self.enabled or os.name!='nt':return True
        import ctypes
        self.active=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        return self.active
    def release(self):
        if self.active:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            self.active=False
