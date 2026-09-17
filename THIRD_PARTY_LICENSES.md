# Third-party code and binaries

This is a distribution summary, not legal advice. The full license terms are
in the linked project files and the bundled copies.

| Component | Use | License and notice |
| --- | --- | --- |
| [Galvani fork](https://github.com/kevinsmia1939/galvani) | Python reader submodule | GPL-3.0-or-later; see `galvani/LICENSE` and source headers. |
| [gamry-parser](https://github.com/bcliang/gamry-parser) | Python reader submodule | MIT; retain `gamry-parser/LICENSE`. |
| [NewareNDA](https://github.com/Solid-Energy-Systems/NewareNDA) | Python reader submodule | BSD-3-Clause; retain `NewareNDA/LICENSE` and its copyright/disclaimer. |
| [MDBTools](https://github.com/mdbtools/mdbtools) | Separate `mdb-export` executable for Arbin files | The `mdb-export` source says GPL-2.0-or-later; the linked library source says GNU Library GPL-2.0-or-later. See `vendor/mdbtools/COPYING` and `COPYING.LIB`. |

The main viewer is GPLv3. It launches `mdb-export` as a separate process and
exchanges CSV text with it; it does not link MDBTools code into the Python app.
The pinned MDBTools v1.0.1 source is available both in the `mdbtools/` Git
submodule and in `vendor/mdbtools/mdbtools-v1.0.1-source.tar.gz`. The Windows
binary comes from [liuxspro's v1.0.1 release](https://github.com/liuxspro/mdbtools-win-build-action/releases/tag/v1.0.1);
the two source patches used by that project are copied into
`vendor/mdbtools/windows/`. The Linux build command is recorded in
`build-mdbtools-linux.sh`. Retain the source archive, patches, build
instructions, and license texts when redistributing either bundled binary.
