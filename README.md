# Electrochemistry Data Viewer

Launch **Electrochemistry Data Viewer** from the applications menu, or double-click
a `.nox`, `.mpr`, or `.mpt` file. It uses the sibling `../galvani` checkout,
including its NOVA and BioLogic readers. The existing app folder and launcher ID
are retained so older shortcuts continue working.
The existing system Python provides PySide6, Matplotlib and NumPy.

For another machine, install `requirements.txt` and the NOX-capable
[Galvani fork](https://github.com/kevinsmia1939/galvani). This checkout
automatically uses a sibling `../galvani` directory when present; otherwise
it imports the installed Galvani package. The current `install.sh` and
`.desktop` launcher contain paths specific to `/home/kevin` and must be
adapted before installing elsewhere.

- Default axes: time (s) horizontally, voltage (V) vertically.
- **Time unit** selects seconds (default), hours, or days for time signals on
  either axis, including step time and BioLogic's raw time columns. Axis labels
  and saved plots follow the selected unit; capacity and source data are unchanged.
- Choose any available recorded signal with the X/Y dropdowns.
- **Capacity (mAh)** is always an axis choice, even without a capacity column.
  **Capacity source** offers Auto (default), Recorded charge only, or Calculated
  from time × current. Auto prefers recorded charge and otherwise calculates.
  Recorded capacity is `abs(charge - charge[0]) / 3.6`; calculated capacity is
  cumulative trapezoidal integration of `abs(current_A)` over seconds, divided
  by 3.6. For constant current this is `abs(I_A) * elapsed_seconds / 3.6`.
  Each step starts at 0 mAh. The time display unit does not affect calculation.
  Missing required signals or invalid integration data skip that step and are
  counted in the status bar. Charge/discharge steps are separate curves; the
  viewer does not infer cycle numbers or correct timestamps.
- BioLogic `.mpr` binary and EC-Lab/BT-Lab `.mpt` text exports are supported.
  All numeric recorded columns remain available. Voltage, time, and current
  also have normalized axis choices (current in A). Curves split on recorded
  `Ns`, half-cycle, cycle-number changes and time resets; without these markers,
  current polarity changes separate steps (1 mA deadband).
  Capacity uses recorded cumulative charge where available, otherwise integrates
  current over time within each step. The step tooltip states its source.
  Unknown MPR binary columns produce an error rather than guessed data.
- Check/uncheck steps; **Active** selects steps with median absolute current
  greater than 1 mA. Missing signals are skipped and counted in the status bar.
- The default legend is outside the axes with columns sized to fit the window.
  Drag it or select a preset. Resizing or changing plot options resets its
  position to the selected preset. For very many steps, select fewer steps or
  hide the legend; the step list remains available. For more than 60 curves,
  outside legends are automatically hidden to avoid consuming the plot area.
- **Save plot…** / Ctrl+S exports PNG, PDF, SVG or JPEG, including the current
  zoom and legend position. The toolbar also supports pan, zoom and saving.
- **Open data…** / Ctrl+O opens another measurement. Opening multiple files from
  the file manager creates a separate window for each file.

Run directly:

```bash
/usr/bin/python3 /home/kevin/Dropbox/Desktop/software/nox-viewer/nox_viewer.py /path/to/measurement.nox
```

Install/re-register the menu entry and file association (no sudo required):

```bash
bash /home/kevin/Dropbox/Desktop/software/nox-viewer/install.sh
```

Installed files:

- `/home/kevin/.local/share/applications/org.kevin.NoxViewer.desktop`
- `/home/kevin/.local/share/mime/packages/metrohm-nova-nox.xml`

The installer associates only the dedicated NOVA and BioLogic MIME types,
not generic binary or text files. To choose another default later, use the file manager's
**Open With** settings.
