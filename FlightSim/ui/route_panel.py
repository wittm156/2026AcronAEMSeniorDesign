"""Minimal route-query panel. Model calls run outside the GUI thread."""
import json
from copy import deepcopy
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from navigation.database import load_database
from navigation.query_model import OllamaQueryModel
from navigation.route_state import route_waypoints


class RouteWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, text, model, parent=None):
        super().__init__(parent)
        self.text, self.model = text, model

    def run(self):
        try:
            database = load_database()
            result = self.model.parse(self.text, database)
            print("[Ollama route] " + json.dumps(result["selected"]), flush=True)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class RoutePanel(QFrame):
    route_selected = pyqtSignal(object)  # Extension point for map drawing / route following.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("routePanel")
        self.setStyleSheet("QFrame#routePanel { border: 2px solid white; background: black; }")
        self.worker = None
        self.selected_route = None
        route_waypoints.clear()
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query = QLineEdit("Shortest route to KSTP")
        self.query.setPlaceholderText("Enter destination airport name or ID")
        self.mode = QLabel("Ollama: qwen3:4b")
        self.button = QPushButton("Plan route")
        layout.addWidget(self.query)
        for widget in (self.mode, self.button):
            row.addWidget(widget)
        layout.addLayout(row)
        self.result = QLabel("Direct routes from KLVN. Enter an airport name or ID.")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        self.button.clicked.connect(self.plan)
        self.query.returnPressed.connect(self.plan)

    def plan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.selected_route = None
        route_waypoints.clear()
        self.result.setText("Planning route…")
        self.button.setEnabled(False)
        model = OllamaQueryModel()
        self.worker = RouteWorker(self.query.text(), model, self)
        self.worker.completed.connect(self.show_route)
        self.worker.failed.connect(lambda message: self.result.setText("Unable to plan: " + message))
        self.worker.finished.connect(lambda: self.button.setEnabled(True))
        self.worker.start()

    def show_route(self, result):
        self.selected_route = result
        route = result["selected"]
        route_waypoints[:] = deepcopy(route["waypoints"])
        self.result.setText(
            f"{result['origin']} → {result['destination']}: {route['distance_nm']:.2f} NM, "
            f"{len(route_waypoints)} waypoints at {route_waypoints[0]['altitude_ft']:.0f} ft MSL.")
        print(f"[Route] {result['origin']} -> {result['destination']}: "
              f"{route['distance_nm']:.2f} NM; {len(route_waypoints)} waypoints; "
              "altitude_ft is constant MSL (visualization only).", flush=True)
        print(json.dumps(route_waypoints, indent=2), flush=True)
        self.route_selected.emit(result)

    def is_busy(self):
        return self.worker is not None and self.worker.isRunning()
