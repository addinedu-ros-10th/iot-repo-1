#!/usr/bin/env python3
# -*- coding: utf-8 -*-



import sys, time
from PyQt6.QtCore import Qt, QEvent, QCoreApplication, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QMessageBox
)

# === 각 앱 클래스 임포트 (환경에 맞게) ===
from iot_project_parking import MainWindow as ParkingMainWindow
from iot_project_access import MyDialog as AccessMainWindow   # access는 QDialog 기반


class _WindowToTabAdapter(QWidget):

    def __init__(self, win: QWidget, parent=None):
        super().__init__(parent)
        self._win = win
        # 원본 윈도우를 이 컨테이너의 자식으로 삼고, 레이아웃에 바로 올린다.
        self._win.setParent(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._win)

    def _graceful_close_child(self):

        if not self._win:
            return

        # 1) close 이벤트 보내기 (각 앱의 closeEvent 내부에서 스레드 정리)
        try:
            ev = QCloseEvent()
            QCoreApplication.sendEvent(self._win, ev)
        except Exception:
            pass

        # 2) 있을 법한 정리 메서드도 추가 호출(방어적)
        for meth in ("stop_detector", "_cleanup_thread", "close"):
            try:
                fn = getattr(self._win, meth, None)
                if callable(fn):
                    fn()
            except Exception:
                pass

        # 3) deleteLater로 파괴 예약
        try:
            self._win.deleteLater()
        except Exception:
            pass

        # 4) 이벤트 처리하여 종료 루틴이 실제로 돌 기회 제공
        QCoreApplication.processEvents()

    def closeEvent(self, e):
        self._graceful_close_child()
        return super().closeEvent(e)


class ControlHub(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IoT Control Hub (Parking + Access)")

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)

        # ---- Parking 탭 ----
        try:
            self.parking_win = ParkingMainWindow()   # QMainWindow 기반
            self.parking_tab = _WindowToTabAdapter(self.parking_win, parent=self)
            self.tabs.addTab(self.parking_tab, "주차(Parking)")
        except Exception as e:
            self.parking_win = None
            self.tabs.addTab(QWidget(), "주차(Parking)")
            QMessageBox.critical(self, "로드 오류", f"Parking 로드 실패: {e}")

        # ---- Access 탭 ----
        try:
            self.access_win = AccessMainWindow()     # QDialog 기반
            self.access_tab = _WindowToTabAdapter(self.access_win, parent=self)
            self.tabs.addTab(self.access_tab, "출입(Access)")
        except Exception as e:
            self.access_win = None
            self.tabs.addTab(QWidget(), "출입(Access)")
            QMessageBox.critical(self, "로드 오류", f"Access 로드 실패: {e}")

        # 시작 탭
        self.tabs.setCurrentIndex(0)

        # 앱 종료 직전 한 번 더 정리(이중 안전장치)
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._graceful_shutdown_all)

    def _graceful_shutdown_all(self):

        for win in (getattr(self, "parking_win", None), getattr(self, "access_win", None)):
            try:
                if win is None:
                    continue
                # close 이벤트 보내기
                ev = QCloseEvent()
                QCoreApplication.sendEvent(win, ev)
            except Exception:
                pass
            # 추가로 stop_detector 등 있으면 호출
            for meth in ("stop_detector", "_cleanup_thread", "close"):
                try:
                    fn = getattr(win, meth, None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass

        # 이벤트 펌프 돌려서 스레드가 종료 기회 얻도록
        for _ in range(3):
            QCoreApplication.processEvents()
            time.sleep(0.05)

    def closeEvent(self, e):
        # 탭 자체도 차례로 닫으며 자식 closeEvent 실행
        try:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, _WindowToTabAdapter):
                    w.close()
        except Exception:
            pass

        # 최종 정리
        self._graceful_shutdown_all()
        return super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    hub = ControlHub()
    hub.resize(1280, 800)
    hub.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
