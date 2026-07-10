# Third-Party Data

The MIT License in this repository applies to the original software and
documentation authored for this project. It does not relicense third-party
input datasets.

## ITC 2019

The paper uses five public International Timetabling Competition 2019
instances and their published solution files:

- `pu-proj-fal19`
- `agh-fal17`
- `muni-pdfx-fal17`
- `pu-d9-fal19`
- `muni-pdf-spr16c`

The competition website publishes these instances for research use, but no
explicit license granting redistribution of the original files or derived
records was located during preparation of release `v1.0.0`. The source XML,
solution XML, and processed day-level JSON records are therefore not mirrored
in this repository. Obtain the source files from the official ITC 2019 website
and use the documented preparation command in `README.md` to regenerate the 25
processed weekday instances locally.

`data_manifests/itc2019_paper_inputs.sha256` identifies the exact source and
solution files used for the paper. The manifest contains only filenames and
checksums, not third-party data.

Official sources:

- Competition and instances: <https://www.itc2019.org/>
- XML format: <https://www.itc2019.org/format>
- Competition results and published solutions: <https://www.itc2019.org/results>

## Lancaster 2023

The `lancs-yr23.xml` source is openly available from Lancaster University
under a CC BY license:

- Matthew Davison (2025), *International Timetabling Competition 2019
  approximation of Lancaster University 2023/2024 term*.
- DOI: <https://doi.org/10.17635/lancaster/researchdata/279>

The 154 MB canonical source file is not duplicated here. Download it from the
publisher and place it at `ITC2019/lancs-yr23.xml` before running the Lancaster
campaign. Its checksum is recorded in `data_manifests/lancaster2023.sha256`.

## Generated Results

The six workbooks under `Numerical experiment results/` are generated solver
outputs of this project. They report aggregate instance and solver statistics;
they do not contain the original XML records or student-level source data.
