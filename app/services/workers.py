"""Infraestructura de tareas en segundo plano para Qt."""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskFailure:
    message: str
    diagnostic: str


class WorkerSignals(QObject):
    result = Signal(object)
    failed = Signal(object)
    progress = Signal(object)
    log = Signal(str, str)
    done = Signal()


class TaskWorker(QRunnable, Generic[T]):
    def __init__(self, function: Callable[[], T], cancel: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()
        self._cancel = cancel
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            value = self.function()
        except Exception as exc:  # la UI recibe un mensaje humano; el detalle queda disponible
            diagnostic = traceback.format_exc()
            logger.error("Fallo en tarea de fondo: %s\n%s", exc, diagnostic)
            self.signals.failed.emit(TaskFailure(str(exc) or exc.__class__.__name__, diagnostic))
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.done.emit()

    def cancel(self) -> None:
        if self._cancel:
            self._cancel()
