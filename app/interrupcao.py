"""Interrupção de operações em andamento.

As portas seriais abertas pelo PYProg ficam registradas; ao interromper, elas são fechadas,
o que faz a leitura ou gravação em curso parar com erro em vez de ficar esperando o rádio.
"""
import threading
import time
import weakref

_portas = weakref.WeakSet()
_trava = threading.Lock()
ultima_abertura = None        # (momento, nome da porta) da última porta que o PYProg tentou abrir


def instala():
    try:
        import serial
    except ImportError:
        return
    if getattr(serial.Serial, "_pyprog_registra", False):
        return
    base = serial.Serial

    class SerialRegistrada(base):
        _pyprog_registra = True

        def open(self):
            global ultima_abertura
            ultima_abertura = (time.monotonic(), self.port)
            super().open()
            with _trava:
                _portas.add(self)

        def close(self):
            with _trava:
                _portas.discard(self)
            super().close()

    serial.Serial = SerialRegistrada


def fecha_portas():
    with _trava:
        abertas = list(_portas)
    for p in abertas:
        try:
            p.cancel_read()
        except Exception:
            pass
        try:
            p.close()
        except Exception:
            pass
    return len(abertas)
