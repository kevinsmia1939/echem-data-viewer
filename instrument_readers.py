"""Adapters from bundled instrument readers to the viewer's dataset interface."""

import os
import platform
from pathlib import Path
from types import SimpleNamespace
import shutil
import threading

import numpy as np
import pandas as pd

from galvani.Nova import NovaDataset


_MDB_PATH_LOCK = threading.Lock()


def bundled_mdb_export():
    """Return our MDBTools executable for a supported platform, if present."""
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        return None
    bundle = Path(__file__).resolve().parent / "vendor" / "mdbtools"
    if platform.system() == "Linux":
        candidate = bundle / "linux-x86_64" / "mdb-export"
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    if platform.system() == "Windows":
        candidate = bundle / "windows" / "mdb-export.exe"
        return candidate if candidate.is_file() else None
    return None


def ensure_mdb_export():
    """Galvani launches `mdb-export` by name; put our copy first on this process's PATH."""
    bundled = bundled_mdb_export()
    if bundled is not None:
        with _MDB_PATH_LOCK:
            paths = os.environ.get("PATH", "").split(os.pathsep)
            if str(bundled.parent) not in paths:
                os.environ["PATH"] = str(bundled.parent) + os.pathsep + os.environ.get("PATH", "")
    if not shutil.which("mdb-export"):
        raise RuntimeError("No usable MDBTools mdb-export found. Reinstall the viewer with "
                           "its bundled tools, or install MDBTools for this platform.")
    return shutil.which("mdb-export")


def _datasets_from_frame(frame, instrument, groups=None, aliases=None, units=None,
                         capacity_columns=None, capacity_factor=1.0):
    """Keep numeric recorded columns and add consistent voltage/current/time aliases."""
    aliases = aliases or {}
    units = units or {}
    capacity_columns = capacity_columns or ()
    if groups is None:
        groups = [(0, len(frame), "")]
    numeric = frame.select_dtypes(include="number").columns
    datasets = []
    for start, stop, detail in groups:
        rows = frame.iloc[start:stop]
        if rows.empty:
            continue
        signals = {key: rows[key].to_numpy(dtype=float, copy=True) for key in numeric}
        signal_units = {key: units.get(key, "") for key in signals}
        for target, (source, factor, unit) in aliases.items():
            if source in signals:
                signals[target] = signals[source] * factor
                signal_units[target] = unit
        charge = _recorded_capacity(rows, capacity_columns)
        if charge is not None:
            signals["EI_0.CalcCharge"] = charge * capacity_factor
            signal_units["EI_0.CalcCharge"] = "C"
        dataset = NovaDataset(f"{instrument} {detail}".strip(), len(datasets) + 1,
                              None, signals, signal_units, {})
        datasets.append(dataset)
    return SimpleNamespace(datasets=datasets)


def _recorded_capacity(rows, columns):
    """Pick the active charge/discharge counter for a contiguous step."""
    choices = [(key, rows[key].to_numpy(dtype=float, copy=True))
               for key in columns if key in rows]
    if not choices:
        return None
    return max(choices, key=lambda pair: np.nanmax(pair[1]) - np.nanmin(pair[1]))[1]


def _step_groups(frame, keys):
    if frame.empty:
        return []
    changed = np.zeros(len(frame) - 1, dtype=bool)
    for key in keys:
        if key in frame:
            values = frame[key].to_numpy()
            changed |= values[1:] != values[:-1]
    if "Time" in frame:
        changed |= np.diff(frame["Time"].to_numpy(dtype=float)) < 0
    cuts = np.r_[0, np.flatnonzero(changed) + 1, len(frame)]
    return [(int(start), int(stop), ", ".join(f"{key}={frame[key].iloc[start]}"
            for key in keys if key in frame)) for start, stop in zip(cuts[:-1], cuts[1:])]


def read_gamry(path):
    from gamry_parser import GamryParser

    parser = GamryParser()
    parser.load(str(path))
    datasets = []
    for index, curve in enumerate(parser.curves, 1):
        time_key = "T" if "T" in curve else "Time" if "Time" in curve else None
        voltage_key = "Vf" if "Vf" in curve else "Vdc" if "Vdc" in curve else None
        current_key = "Im" if "Im" in curve else "Idc" if "Idc" in curve else None
        aliases = {}
        if time_key:
            aliases["CalcTime"] = (time_key, 1, "s")
        if voltage_key:
            aliases["EI_0.CalcPotential"] = (voltage_key, 1, "V")
        if current_key:
            aliases["EI_0.CalcCurrent"] = (current_key, 1, "A")
        adapted = _datasets_from_frame(curve, "Gamry", aliases=aliases,
                                       units=parser._curve_units)
        for dataset in adapted.datasets:
            dataset.command = f"Gamry curve {index}"
            datasets.append(dataset)
    return SimpleNamespace(datasets=datasets)


def read_neware(path):
    from NewareNDA.NewareNDA import read_nda
    from NewareNDA.NewareNDAx import read_ndax

    # The bundled library's synthetic cycle calculation writes to a read-only
    # pandas 3 array. The recorded Cycle and Step fields are sufficient here.
    # Dispatch ourselves because the upstream `read` dispatcher compares suffixes
    # case-sensitively, while the viewer's picker accepts uppercase extensions.
    frame = (read_nda(str(path), software_cycle_number=False) if path.suffix.lower() == ".nda"
             else read_ndax(str(path), software_cycle_number=False))
    aliases = {"CalcTime": ("Time", 1, "s"),
               "EI_0.CalcPotential": ("Voltage", 1, "V"),
               "EI_0.CalcCurrent": ("Current(mA)", 0.001, "A")}
    units = {"Time": "s", "Voltage": "V", "Current(mA)": "mA",
             "Charge_Capacity(mAh)": "mAh", "Discharge_Capacity(mAh)": "mAh"}
    return _datasets_from_frame(frame, "Neware", _step_groups(frame, ("Cycle", "Step")),
                                aliases, units,
                                ("Charge_Capacity(mAh)", "Discharge_Capacity(mAh)"), 3.6)


def read_arbin(path):
    ensure_mdb_export()
    from galvani.res2sqlite import convert_arbin_to_sqlite

    connection = convert_arbin_to_sqlite(str(path))
    try:
        frame = pd.read_sql_query('SELECT * FROM "Channel_Normal_Table" '
                                  'ORDER BY "Test_ID", "Data_Point"', connection)
    finally:
        connection.close()
    aliases = {"CalcTime": ("Test_Time", 1, "s"),
               "Correctedtime": ("Step_Time", 1, "s"),
               "EI_0.CalcPotential": ("Voltage", 1, "V"),
               "EI_0.CalcCurrent": ("Current", 1, "A")}
    units = {"Test_Time": "s", "Step_Time": "s", "Voltage": "V",
             "Current": "A", "Charge_Capacity": "Ah", "Discharge_Capacity": "Ah"}
    return _datasets_from_frame(frame, "Arbin", _step_groups(frame, ("Test_ID", "Cycle_Index", "Step_Index")),
                                aliases, units, ("Charge_Capacity", "Discharge_Capacity"), 3600)
