"""Run headlessly: QT_QPA_PLATFORM=offscreen python3 -m unittest -v test_viewer."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from matplotlib.backend_bases import MouseEvent
from echem_data_viewer import QtWidgets, Viewer, FileLoader, signal_values, CAPACITY, FORK, read_file, biologic_datasets
from galvani.Nova import NovaDataset
from types import SimpleNamespace


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.viewer = Viewer()
        self.viewer.path = Path("example.nox")
        datasets = []
        for i in range(43):
            signals = {
                "CalcTime": np.arange(3) + i * 3,
                "EI_0.CalcPotential": np.array([0.1, 0.2, 0.3]),
            }
            if i % 3:
                sign = 1 if i % 2 else -1
                signals["EI_0.CalcCurrent"] = np.full(3, sign * 0.3)
                signals["EI_0.CalcCharge"] = sign * np.array([10, 13.6, 17.2])
            datasets.append(NovaDataset("test", i, None, signals, {}, {}))
        self.viewer.show()
        self.viewer.set_data(SimpleNamespace(datasets=datasets))
        self.app.processEvents()
        self.viewer.canvas.draw()

    def test_bundled_galvani_is_used(self):
        import galvani
        self.assertTrue(Path(galvani.__file__).resolve().is_relative_to(FORK.resolve()))

    def tearDown(self):
        self.viewer.close()
        self.app.processEvents()

    def test_defaults_and_nonoverlapping_legend(self):
        v = self.viewer
        self.assertEqual(v.x_axis.currentText(), "Time (s)")
        self.assertEqual(v.y_axis.currentText(), "Voltage (V)")
        self.assertEqual(len(v.ax.lines), 43)
        renderer = v.canvas.get_renderer()
        self.assertFalse(v.legend.get_window_extent(renderer).overlaps(v.ax.get_window_extent(renderer)))
        boxes = [text.get_window_extent(renderer) for text in v.legend.get_texts()]
        for i, box in enumerate(boxes):
            for other in boxes[i + 1:]:
                self.assertFalse(box.overlaps(other))

    def test_capacity_selection_and_skipped_signals(self):
        v = self.viewer
        v.x_axis.setCurrentIndex(v.x_axis.findData(CAPACITY))
        self.assertEqual(len(v.ax.lines), 28)
        for line in v.ax.lines:
            np.testing.assert_allclose(line.get_xdata(), [0, 1, 2])
        v.select_steps("none")
        self.assertEqual(len(v.ax.lines), 0)
        self.assertFalse(v.save_button.isEnabled())
        v.select_steps("active")
        self.assertEqual(len(v.ax.lines), 28)

    def test_drag_legend_and_export(self):
        v = self.viewer
        renderer = v.canvas.get_renderer()
        before = v.legend.get_window_extent(renderer)
        x, y = before.x0 + before.width / 2, before.y0 + before.height / 2
        for name, px, py, button in (
            ("button_press_event", x, y, 1),
            ("motion_notify_event", x - 40, y - 30, 1),
            ("button_release_event", x - 40, y - 30, 1),
        ):
            event = MouseEvent(name, v.canvas, px, py, button=button)
            v.canvas.callbacks.process(name, event)
        v.canvas.draw()
        after = v.legend.get_window_extent(v.canvas.get_renderer())
        self.assertGreater(abs(after.x0 - before.x0), 10)
        with tempfile.TemporaryDirectory(prefix="echem-data-viewer-test-") as folder:
            for suffix, label in (("png", "PNG"), ("pdf", "PDF"), ("svg", "SVG")):
                target = Path(folder) / f"export.{suffix}"
                with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(target), f"{label} (*.{suffix})")):
                    v.save_plot()
                self.assertGreater(target.stat().st_size, 100)

    def test_legend_presets(self):
        v = self.viewer
        for i in range(v.legend_position.count()):
            v.legend_position.setCurrentIndex(i)
            v.canvas.draw()
            self.assertEqual(v.legend is None, v.legend_position.currentData() == "hidden")

    def test_real_file_async_and_invalid_file(self):
        v = self.viewer
        path = Path('/home/kevin/Dropbox/UAntwerp/PhD_thesis/solid_booster_pulsatile_flow/solid_booster_potentiostat/data/cycling_add_lfp_wrong_time.nox')
        if not path.exists():
            self.skipTest("Real-file fixture no longer present")
        v.open_file(path)
        deadline = time.monotonic() + 60
        while v.loader.isRunning() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertFalse(v.loader.isRunning())
        self.app.processEvents()
        self.assertEqual(v.path, path)
        self.assertEqual(len(v.datasets), 43)
        self.assertEqual(len(v.ax.lines), 43)
        with tempfile.NamedTemporaryFile(suffix=".nox") as invalid:
            failures = []
            worker = FileLoader(Path(invalid.name), v)
            worker.failed.connect(failures.append)
            worker.start()
            while worker.isRunning():
                self.app.processEvents()
                time.sleep(0.01)
            self.app.processEvents()
            self.assertTrue(failures)

    def test_mpt_and_normalized_units(self):
        data = read_file(Path(__file__).parent / "fixtures/example.mpt")
        self.assertEqual(len(data.datasets), 2)
        for dataset, sign in zip(data.datasets, [1, -1]):
            np.testing.assert_allclose(dataset["EI_0.CalcCurrent"], sign * 0.1)
            np.testing.assert_allclose(signal_values(dataset, CAPACITY), [0, 1 / 36, 1 / 18])
            self.assertIn("I/mA", dataset.signal_names)

    def test_capacity_integration_fallback(self):
        rows = np.array([(0, .1, 100), (36, .2, 100), (72, .3, 100)],
                        dtype=[("time/s", float), ("Ewe/V", float), ("I/mA", float)])
        dataset = biologic_datasets(rows).datasets[0]
        np.testing.assert_allclose(signal_values(dataset, CAPACITY), [0, 1, 2])
        self.assertIn("integration", dataset.command)

    def test_nox_capacity_without_recorded_charge_and_source_choice(self):
        v = self.viewer
        signals = {"CalcTime": np.array([10., 46., 82.]),
                   "EI_0.CalcPotential": np.array([.1, .2, .3]),
                   "EI_0.CalcCurrent": np.full(3, -.1)}
        dataset = NovaDataset("no recorded charge", 1, None, signals, {}, {})
        v.set_data(SimpleNamespace(datasets=[dataset]))
        v.x_axis.setCurrentIndex(v.x_axis.findData(CAPACITY))
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), [0, 1, 2])
        v.capacity_source.setCurrentIndex(v.capacity_source.findData("recorded"))
        self.assertEqual(len(v.ax.lines), 0)
        v.capacity_source.setCurrentIndex(v.capacity_source.findData("calculated"))
        v.time_unit.setCurrentIndex(2)
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), [0, 1, 2])
        signals["EI_0.CalcCharge"] = np.array([100., 107.2, 114.4])
        v.capacity_source.setCurrentIndex(v.capacity_source.findData("auto"))
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), [0, 2, 4])
        v.capacity_source.setCurrentIndex(v.capacity_source.findData("calculated"))
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), [0, 1, 2])

    def test_variable_current_integration_and_invalid_time(self):
        dataset = NovaDataset("test", 1, None,
                              {"CalcTime": np.array([0., 36., 108.]),
                               "EI_0.CalcCurrent": np.array([.1, .2, .4])}, {}, {})
        np.testing.assert_allclose(signal_values(dataset, CAPACITY), [0, 1.5, 7.5])
        dataset.signals["CalcTime"] = np.array([0., 36., 20.])
        with self.assertRaises(ValueError):
            signal_values(dataset, CAPACITY, "calculated")

    def test_derived_biologic_charge_is_not_treated_as_recorded(self):
        rows = np.array([(0, .1, 100), (36, .2, 100)],
                        dtype=[("time/s", float), ("Ewe/V", float), ("I/mA", float)])
        dataset = biologic_datasets(rows).datasets[0]
        with self.assertRaises(ValueError):
            signal_values(dataset, CAPACITY, "recorded")

    def test_time_units_on_both_axes(self):
        v = self.viewer
        original = v.datasets[0]["CalcTime"].copy()
        for index, symbol, divisor in ((0, "s", 1), (1, "h", 3600), (2, "d", 86400), (0, "s", 1)):
            v.time_unit.setCurrentIndex(index)
            np.testing.assert_allclose(v.ax.lines[0].get_xdata(), original / divisor)
            np.testing.assert_allclose(v.ax.lines[0].get_ydata(), [.1, .2, .3])
            self.assertEqual(v.ax.get_xlabel(), f"Time ({symbol})")
        v.y_axis.setCurrentIndex(v.y_axis.findData("CalcTime"))
        v.time_unit.setCurrentIndex(2)
        np.testing.assert_allclose(v.ax.lines[0].get_ydata(), original / 86400)
        self.assertEqual(v.ax.get_ylabel(), "Time (d)")
        np.testing.assert_array_equal(v.datasets[0]["CalcTime"], original)

    def test_biologic_raw_time_and_capacity_unaffected(self):
        v = self.viewer
        v.set_data(read_file(Path(__file__).parent / "fixtures/example.mpt"))
        v.x_axis.setCurrentIndex(v.x_axis.findData("time/s"))
        v.time_unit.setCurrentIndex(1)
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), np.arange(3) / 3600)
        self.assertEqual(v.ax.get_xlabel(), "time/h")
        v.x_axis.setCurrentIndex(v.x_axis.findData(CAPACITY))
        np.testing.assert_allclose(v.ax.lines[0].get_xdata(), [0, 1 / 36, 1 / 18])

    def test_all_example_mpr_files(self):
        folder = Path('/home/kevin/Dropbox/UAntwerp/PhD_thesis/copper_flow_battery/data')
        paths = list(folder.glob('*.mpr'))
        if not paths:
            self.skipTest("No BioLogic fixtures present")
        for path in paths:
            with self.subTest(file=path.name):
                data = read_file(path)
                self.assertTrue(data.datasets)
                self.assertTrue(all("CalcTime" in d and "EI_0.CalcPotential" in d for d in data.datasets))
                self.viewer.path = path
                self.viewer.set_data(data)
                self.viewer.canvas.draw()
                self.assertEqual(len(self.viewer.ax.lines), len(data.datasets))
                for dataset in data.datasets:
                    if "EI_0.CalcCharge" in dataset:
                        self.assertEqual(signal_values(dataset, CAPACITY)[0], 0)


if __name__ == "__main__":
    unittest.main()
