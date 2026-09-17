#!/usr/bin/python3
"""Desktop viewer for Metrohm NOVA and BioLogic files using Galvani."""
from pathlib import Path
from types import SimpleNamespace
import io
import math
import sys

from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

FORK = Path(__file__).resolve().parent / "galvani"
if not (FORK / "galvani" / "Nova.py").is_file():
    raise RuntimeError(
        "Bundled Galvani is missing. Run 'git submodule update --init --recursive' "
        "in the viewer directory, then restart the app."
    )
sys.path.insert(0, str(FORK))

CAPACITY = "__capacity_mah__"
TIME_UNITS = (("Seconds (s)", "s", 1.0), ("Hours (h)", "h", 3600.0),
              ("Days (d)", "d", 86400.0))
APP_NAME = "Electrochemistry Data Viewer"
KNOWN = {
    "CalcTime": "Time (s)",
    "EI_0.CalcPotential": "Voltage (V)",
    "EI_0.CalcCurrent": "Current (A)",
    "EI_0.CalcCharge": "Charge (C)",
    "Correctedtime": "Step time (s)",
    "Index": "Point index",
    "EI_0.CalcPower": "Power (W)",
    CAPACITY: "Capacity (mAh; each step starts at 0)",
}


def read_file(path):
    from galvani import NOXfile, MPRfile, MPTfile
    path = Path(path)
    if path.suffix.lower() == ".nox":
        nox = NOXfile(path)
    elif path.suffix.lower() == ".mpr":
        # Keep strict column checking: unknown binary fields must not be guessed.
        with path.open("rb") as stream:
            nox = biologic_datasets(MPRfile(stream).data)
    elif path.suffix.lower() == ".mpt":
        # Galvani expects CRLF. Accept LF exports without altering the source file.
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        try:
            data, _ = MPTfile(io.BytesIO(raw), encoding="utf-8-sig")
        except UnicodeDecodeError:
            data, _ = MPTfile(io.BytesIO(raw), encoding="cp1252")
        nox = biologic_datasets(data)
    else:
        raise ValueError("Supported formats: NOVA .nox, BioLogic .mpr and .mpt")
    if not nox.datasets:
        raise ValueError("This file contains no readable measurement datasets.")
    return nox


def biologic_datasets(data):
    """Adapt Galvani's BioLogic table to the viewer's aligned-signal interface."""
    from galvani.Nova import NovaDataset
    data = np.atleast_1d(data)
    if not len(data):
        return SimpleNamespace(datasets=[])
    names = data.dtype.names or ()
    changed = np.zeros(len(data) - 1, dtype=bool)
    boundaries = [key for key in ("Ns", "half cycle", "cycle number") if key in names]
    for key in boundaries:
        changed |= data[key][1:] != data[key][:-1]
    if "time/s" in names:
        changed |= np.diff(data["time/s"]) < 0
    current_key = next((key for key in ("I/mA", "<I>/mA", "I/A") if key in names), None)
    if not boundaries and current_key:
        current = data[current_key] * (0.001 if current_key.endswith("/mA") else 1)
        polarity = np.where(current > 0.001, 1, np.where(current < -0.001, -1, 0))
        changed |= polarity[1:] != polarity[:-1]
    cuts = np.r_[0, np.flatnonzero(changed) + 1, len(data)]
    datasets = []
    for start, stop in zip(cuts[:-1], cuts[1:]):
        rows = data[start:stop]
        signals = {key: rows[key] for key in names if rows[key].dtype.kind in "biuf"}
        units = {key: key.rsplit("/", 1)[1] if "/" in key else "" for key in signals}
        aliases = {"CalcTime": ("time/s",), "EI_0.CalcPotential": ("Ewe/V", "<Ewe>/V", "Ecell/V"),
                   "EI_0.CalcPower": ("P/W",), "Correctedtime": ("step time/s",)}
        for target, choices in aliases.items():
            source = next((key for key in choices if key in signals), None)
            if source:
                signals[target] = signals[source]
                units[target] = units[source]
        if current_key:
            signals["EI_0.CalcCurrent"] = rows[current_key] * (0.001 if current_key.endswith("/mA") else 1)
            units["EI_0.CalcCurrent"] = "A"
        charge_key = next((key for key in ("(Q-Qo)/mA.h", "(Q-Qo)/C", "Q charge/discharge/mA.h") if key in signals), None)
        capacity_source = "unavailable"
        if charge_key:
            signals["EI_0.CalcCharge"] = signals[charge_key] * (3.6 if charge_key.endswith("/mA.h") else 1)
            capacity_source = f"recorded {charge_key}"
        elif "CalcTime" in signals and "EI_0.CalcCurrent" in signals:
            time_s, current_a = signals["CalcTime"], signals["EI_0.CalcCurrent"]
            charge = np.r_[0.0, np.cumsum(0.5 * (current_a[1:] + current_a[:-1]) * np.diff(time_s))]
            signals["EI_0.CalcCharge"] = charge
            capacity_source = "current–time integration"
        if "EI_0.CalcCharge" in signals:
            units["EI_0.CalcCharge"] = "C"
        details = ", ".join(f"{key}={rows[key][0]:g}" for key in boundaries)
        dataset = NovaDataset(f"BioLogic {details}; capacity: {capacity_source}", len(datasets) + 1,
                              None, signals, units, {})
        dataset.charge_is_calculated = capacity_source == "current–time integration"
        datasets.append(dataset)
    return SimpleNamespace(datasets=datasets)


def recorded_charge_available(dataset):
    return "EI_0.CalcCharge" in dataset and not getattr(dataset, "charge_is_calculated", False)


def capacity_available(dataset, source):
    recorded = recorded_charge_available(dataset)
    calculated = "CalcTime" in dataset and "EI_0.CalcCurrent" in dataset
    return recorded if source == "recorded" else calculated if source == "calculated" else recorded or calculated


def signal_values(dataset, key, capacity_source="auto"):
    if key == CAPACITY:
        if capacity_source == "recorded" or (capacity_source == "auto" and recorded_charge_available(dataset)):
            if not recorded_charge_available(dataset):
                raise ValueError("No recorded charge available for this step")
            charge = np.asarray(dataset["EI_0.CalcCharge"], dtype=float)
            return np.abs(charge - charge[0]) / 3.6 if len(charge) else charge
        time_s = np.asarray(dataset["CalcTime"], dtype=float)
        current_a = np.asarray(dataset["EI_0.CalcCurrent"], dtype=float)
        if len(time_s) != len(current_a) or not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(current_a)):
            raise ValueError("Capacity calculation requires aligned, finite time and current")
        delta_t = np.diff(time_s)
        if np.any(delta_t < 0):
            raise ValueError("Capacity calculation requires nondecreasing time within a step")
        if not len(time_s):
            return time_s
        interval_mah = 0.5 * (np.abs(current_a[1:]) + np.abs(current_a[:-1])) * delta_t / 3.6
        return np.r_[0.0, np.cumsum(interval_mah)]
    return np.asarray(dataset[key], dtype=float)


def is_time_signal(key):
    return key in ("CalcTime", "Correctedtime") or (
        isinstance(key, str) and "time" in key.casefold() and key.endswith("/s")
    )


def axis_label(key, label, time_unit):
    if not is_time_signal(key):
        return label
    return label.replace("(s)", f"({time_unit})").replace("/s", f"/{time_unit}")


class FileLoader(QtCore.QThread):
    loaded = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, path, parent):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.loaded.emit(read_file(self.path))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class Viewer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1400, 850)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon.fromTheme("office-chart-line"))
        self.nox = None
        self.path = None
        self.pending_path = None
        self.loader = None
        self.legend = None
        self.datasets = []

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        controls = QtWidgets.QHBoxLayout()
        self.open_button = QtWidgets.QPushButton("Open data…")
        self.open_button.clicked.connect(self.choose_file)
        controls.addWidget(self.open_button)
        self.x_axis = QtWidgets.QComboBox()
        self.y_axis = QtWidgets.QComboBox()
        for label, combo in (("X axis:", self.x_axis), ("Y axis:", self.y_axis)):
            controls.addWidget(QtWidgets.QLabel(label))
            controls.addWidget(combo, 1)
            combo.currentIndexChanged.connect(self.redraw)
        controls.addWidget(QtWidgets.QLabel("Time unit:"))
        self.time_unit = QtWidgets.QComboBox()
        for label, symbol, divisor in TIME_UNITS:
            self.time_unit.addItem(label, (symbol, divisor))
        self.time_unit.setToolTip("Applies to all time signals on either axis; source data is unchanged.")
        self.time_unit.currentIndexChanged.connect(self.redraw)
        controls.addWidget(self.time_unit)
        self.save_button = QtWidgets.QPushButton("Save plot…")
        self.save_button.clicked.connect(self.save_plot)
        controls.addWidget(self.save_button)
        layout.addLayout(controls)

        splitter = QtWidgets.QSplitter()
        sidebar = QtWidgets.QWidget()
        side = QtWidgets.QVBoxLayout(sidebar)
        side.addWidget(QtWidgets.QLabel("Measurement steps"))
        buttons = QtWidgets.QHBoxLayout()
        for label, mode in (("All", "all"), ("None", "none"), ("Active", "active")):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda checked=False, m=mode: self.select_steps(m))
            buttons.addWidget(button)
        side.addLayout(buttons)
        self.step_list = QtWidgets.QListWidget()
        self.step_list.itemChanged.connect(self.redraw)
        side.addWidget(self.step_list, 1)
        side.addWidget(QtWidgets.QLabel("Legend position (also drag it):"))
        self.legend_position = QtWidgets.QComboBox()
        for label, value in (
            ("Outside right (default)", "outside right upper"),
            ("Outside bottom", "outside lower center"),
            ("Automatic inside", "best"),
            ("Upper right", "upper right"), ("Upper left", "upper left"),
            ("Lower right", "lower right"), ("Lower left", "lower left"),
            ("Hidden", "hidden"),
        ):
            self.legend_position.addItem(label, value)
        self.legend_position.currentIndexChanged.connect(self.redraw)
        side.addWidget(self.legend_position)
        side.addWidget(QtWidgets.QLabel("Capacity source:"))
        self.capacity_source = QtWidgets.QComboBox()
        self.capacity_source.addItem("Auto: recorded, otherwise calculated", "auto")
        self.capacity_source.addItem("Recorded charge only", "recorded")
        self.capacity_source.addItem("Calculated from time × current", "calculated")
        self.capacity_source.setToolTip("Applies when Capacity is selected on either axis. Calculation always uses seconds and amperes.")
        self.capacity_source.currentIndexChanged.connect(self.redraw)
        side.addWidget(self.capacity_source)
        self.grid = QtWidgets.QCheckBox("Show grid")
        self.grid.setChecked(True)
        self.grid.toggled.connect(self.redraw)
        side.addWidget(self.grid)
        note = QtWidgets.QLabel(
            "Capacity starts at 0 for each step. Choose recorded charge or calculate "
            "by integrating |current| over time. Auto uses recorded charge when available.\n\n"
            "Active selects steps with median |current| > 1 mA. Steps missing a selected "
            "signal are skipped.\n\nUse the plot toolbar to zoom, pan, and reset the view."
        )
        note.setWordWrap(True)
        side.addWidget(note)
        splitter.addWidget(sidebar)

        plot_widget = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_widget)
        self.figure = Figure(layout="constrained", facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas, 1)
        splitter.addWidget(plot_widget)
        splitter.setSizes([270, 1130])
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Open a .nox, .mpr or .mpt file to begin.")
        self.save_button.setEnabled(False)
        self.canvas.mpl_connect("resize_event", self.on_resize)

        open_action = QtGui.QAction("Open…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.choose_file)
        save_action = QtGui.QAction("Save plot…", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_plot)
        menu = self.menuBar().addMenu("File")
        menu.addActions([open_action, save_action])

    def choose_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open electrochemistry measurement", str(self.path.parent) if self.path else "",
            "Electrochemistry files (*.nox *.NOX *.mpr *.MPR *.mpt *.MPT);;"
            "NOVA (*.nox *.NOX);;BioLogic (*.mpr *.MPR *.mpt *.MPT);;All files (*)"
        )
        if path:
            self.open_file(Path(path))

    def open_file(self, path):
        if self.loader and self.loader.isRunning():
            return
        self.pending_path = Path(path)
        self.open_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.statusBar().showMessage(f"Reading {self.pending_path.name}…")
        self.loader = FileLoader(self.pending_path, self)
        self.loader.loaded.connect(self.set_data)
        self.loader.failed.connect(self.show_error)
        self.loader.finished.connect(lambda: self.open_button.setEnabled(True))
        self.loader.start()

    def show_error(self, text):
        self.pending_path = None
        self.save_button.setEnabled(bool(self.ax.lines))
        self.statusBar().showMessage("Could not read the file.")
        QtWidgets.QMessageBox.critical(self, "Unable to open measurement", text)

    def set_data(self, nox):
        if self.pending_path is not None:
            self.path = self.pending_path
            self.pending_path = None
        self.nox = nox
        # Preserve each dataset internally; sorting changes only display order.
        self.datasets = sorted(nox.datasets, key=lambda d: (
            float(d["CalcTime"][0]) if "CalcTime" in d and len(d["CalcTime"]) else math.inf
        ))
        keys = dict.fromkeys(key for d in self.datasets for key in d.signal_names)
        # A derived axis is selectable even when it is not a recorded column.
        keys[CAPACITY] = None
        for combo, default in ((self.x_axis, "CalcTime"), (self.y_axis, "EI_0.CalcPotential")):
            combo.blockSignals(True)
            combo.clear()
            for key in keys:
                unit = next((d.units.get(key, "") for d in self.datasets if key in d), "")
                combo.addItem(KNOWN.get(key, f"{key} ({unit})" if unit else key), key)
            index = combo.findData(default)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for i, dataset in enumerate(self.datasets, 1):
            current = dataset.signals.get("EI_0.CalcCurrent")
            suffix = ""
            if current is not None and len(current):
                suffix = f" · {np.median(current) * 1000:+.2f} mA"
            item = QtWidgets.QListWidgetItem(f"Step {i} · {len(dataset):,} points{suffix}")
            item.setToolTip(f"{dataset.command}\n" + "\n".join(dataset.signal_names))
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            self.step_list.addItem(item)
        self.step_list.blockSignals(False)
        self.setWindowTitle(f"{self.path.name} — {APP_NAME}")
        self.redraw()

    def select_steps(self, mode):
        self.step_list.blockSignals(True)
        for i, dataset in enumerate(self.datasets):
            current = dataset.signals.get("EI_0.CalcCurrent")
            active = current is not None and len(current) and abs(float(np.median(current))) > 0.001
            selected = mode == "all" or (mode == "active" and active)
            self.step_list.item(i).setCheckState(
                QtCore.Qt.CheckState.Checked if selected else QtCore.Qt.CheckState.Unchecked
            )
        self.step_list.blockSignals(False)
        self.redraw()

    def redraw(self, *_):
        if self.nox is None:
            return
        symbol, divisor = self.time_unit.currentData()
        for combo in (self.x_axis, self.y_axis):
            combo.blockSignals(True)
            for index in range(combo.count()):
                key = combo.itemData(index)
                if is_time_signal(key):
                    combo.setItemText(index, axis_label(key, KNOWN.get(key, key), symbol))
            combo.blockSignals(False)
        self.remove_legend()
        self.ax.clear()
        xkey, ykey = self.x_axis.currentData(), self.y_axis.currentData()
        capacity_source = self.capacity_source.currentData()
        skipped = 0
        for i, dataset in enumerate(self.datasets):
            if self.step_list.item(i).checkState() != QtCore.Qt.CheckState.Checked:
                continue
            if not all(capacity_available(dataset, capacity_source) if key == CAPACITY else key in dataset
                       for key in (xkey, ykey)):
                skipped += 1
                continue
            try:
                x, y = (signal_values(dataset, key, capacity_source) for key in (xkey, ykey))
            except ValueError:
                skipped += 1
                continue
            if is_time_signal(xkey):
                x = x / divisor
            if is_time_signal(ykey):
                y = y / divisor
            if len(x) != len(y):
                skipped += 1
                continue
            # NaNs remain gaps, so missing values never join unrelated points.
            x = np.where(np.isfinite(x), x, np.nan)
            y = np.where(np.isfinite(y), y, np.nan)
            self.ax.plot(x, y, linewidth=1, label=f"Step {i + 1}")
        self.ax.set_xlabel(self.x_axis.currentText())
        self.ax.set_ylabel(self.y_axis.currentText())
        self.ax.set_title(self.path.name, fontsize=10)
        self.ax.grid(self.grid.isChecked(), alpha=0.25)
        if xkey == CAPACITY:
            self.ax.set_xlim(left=0)
        self.make_legend()
        self.toolbar.update()
        self.canvas.draw_idle()
        self.save_button.setEnabled(bool(self.ax.lines))
        self.statusBar().showMessage(
            f"{len(self.ax.lines)} steps plotted · {skipped} selected steps missing compatible or valid signals. "
            + ("Legend hidden for >60 curves; use the step list to select fewer."
               if len(self.ax.lines) > 60 and self.legend_position.currentData().startswith("outside")
               else "Drag the legend to reposition it.")
        )

    def remove_legend(self):
        if self.legend is not None:
            self.legend.set_draggable(False)
            self.legend.remove()
            self.legend = None

    def make_legend(self):
        handles, labels = self.ax.get_legend_handles_labels()
        position = self.legend_position.currentData()
        if not handles or position == "hidden":
            return
        if len(handles) > 60 and position.startswith("outside"):
            return  # Huge cycling runs must not let the legend consume the plot.
        if position.startswith("outside"):
            # Allocate columns to fit the available height. Constrained layout
            # reserves a separate area for the figure legend, away from data.
            max_rows = max(4, int(self.figure.get_figheight() * 72 / 15) - 5)
            columns = max(1, math.ceil(len(handles) / max_rows))
            if position == "outside lower center":
                columns = max(columns, max(1, int(self.figure.get_figwidth() * 72 / 90)))
            self.legend = self.figure.legend(handles, labels, loc=position,
                                             ncols=columns, fontsize=8, title="Steps")
        else:
            self.legend = self.ax.legend(loc=position, fontsize=8,
                                         ncols=max(1, math.ceil(len(handles) / 20)))
        self.legend.set_draggable(True)

    def on_resize(self, _):
        if self.nox and self.legend_position.currentData().startswith("outside"):
            self.remove_legend()
            self.make_legend()
            self.canvas.draw_idle()

    def save_plot(self):
        if not self.ax.lines:
            return
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save plot", str(self.path.with_suffix(".png")),
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;JPEG (*.jpg)"
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            suffix = {"PNG": ".png", "PDF": ".pdf", "SVG": ".svg", "JPEG": ".jpg"}
            target = target.with_suffix(suffix[selected_filter.split()[0]])
            if target.exists() and QtWidgets.QMessageBox.question(
                self, "Overwrite plot?", f"Replace {target}?"
            ) != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        try:
            self.figure.savefig(target, dpi=300, bbox_inches="tight")
            self.statusBar().showMessage(f"Saved {target}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))

    def closeEvent(self, event):
        if self.loader and self.loader.isRunning():
            self.statusBar().showMessage("Please wait for file reading to finish before closing.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    windows = []
    for path in sys.argv[1:] or [None]:
        window = Viewer()
        windows.append(window)
        window.show()
        if path:
            window.open_file(Path(path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
