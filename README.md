# AnnoPilot

**Intelligent Annotation Review Assistant — Review smarter, not more.**

AnnoPilot turns existing annotations into an explainable QC plan. It estimates sample review effort, selects a QC subset, balances reviewer workloads, orders each reviewer's queue, and stores human findings. It runs locally on CPU without an external AI service.

**Difficulty estimates review effort. It does not predict whether an annotation is correct or incorrect.** A hard sample can be correctly annotated. Only a person records No Issue or Issue Found.

## Problem and solution

Reviewing every sample is expensive, and equal sample counts can hide unequal review effort. AnnoPilot combines media heuristics and task-specific annotation analysis to help people decide what to inspect and who should inspect it.

## Workflow

Dataset → Import/normalize → Media + annotation analysis → Difficulty → Dataset health → Smart Sampling → Workload balance → Reviewer priority queue → Human review → CSV export.

Upload your own annotations and optional media. There is no demo loader, seeded reviewer, fake analytics or production test data. Multiple datasets can be uploaded and selected from the header.

## Run locally on Windows

The project root is `F:\VinAI\Workspace\Tool\AnnoPilot` on the development machine. Runtime paths are relative to the repository or supplied through environment variables.

Requirements: Python 3.9+ (3.11 recommended on a new machine), Node.js 22+, npm.

One-command setup/start from the project root:

```powershell
.\Start-AnnoPilot.ps1 -Install
```

Subsequent starts: `.\Start-AnnoPilot.ps1`. This launches hidden local server processes, prints their IDs, and writes ignored logs. It refuses to overwrite existing listeners on 3000/8000.

Or use two terminals:

```powershell
Set-Location "F:\VinAI\Workspace\Tool\AnnoPilot\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
Set-Location "F:\VinAI\Workspace\Tool\AnnoPilot\frontend"
npm ci
npm run dev
```

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- Swagger: http://localhost:8000/docs

## Docker

```powershell
docker compose up --build
```

Docker serves the built frontend through Nginx on 3000 and FastAPI on 8000. Nginx proxies `/api` to `backend:8000`; the browser never needs to resolve Docker service names. SQLite lives in the named `database` volume; uploads/exports are bind-mounted. `docker compose down` preserves the named database volume; removing volumes erases it.

**Verification:** `docker compose config --quiet` passed. Container build/start has not been verified because Docker Desktop was manually paused on this machine. Unpause it before running Compose. Stop the local servers first if they occupy 3000/8000. Local and Docker SQLite stores are separate.

## Format and task support

| Format | Implemented tasks | Scope and limitations |
| --- | --- | --- |
| CVAT images XML | BBox 2D, polygons, points, mixed | Attributes, occlusion and source metadata retained. CVAT points do not invent visibility. Video tracks, ellipse, polyline, skeleton and CVAT raster masks are unsupported and reported. |
| COCO JSON | BBox, polygon segmentation, keypoints, mixed | Keypoint visibility and category point names retained. RLE masks are preserved in their source representation; mask boundary/area/crowding metrics and rendering are unavailable. Geometry preference per source instance: keypoints, then segmentation, then bbox; avoids scoring the same instance three times. Multiple polygon rings are separate normalized shapes. |
| YOLO detection TXT | BBox 2D | Standard five-field `class cx cy w h` only. Exactly one matching image is required to convert normalized coordinates to pixels. Optional `classes.txt` supplies class names; otherwise source numeric IDs are preserved. YOLO segmentation/pose exports are unsupported. |
| KITTI label TXT | Cuboid 3D | Standard 15+ fields, truncation, occlusion, original 2D box, alpha and geometry retained. DontCare records excluded. Dimensions are height/width/length; position is bottom center in the rectified camera frame, x right/y down/z forward. No sensor transform is invented. |

JPG/JPEG/PNG are decoded and analyzed. BIN/PCD files can be uploaded and retained/matched as sensor media; point-cloud decoding, calibration, point-in-cuboid density and interactive 3D visualization are not implemented. Cuboid review uses normalized metadata and available features.

Annotation samples remain when media is missing. Names match by relative suffix, then unique basename, then unique stem. Ambiguous matches produce availability warnings, not an arbitrary image. Images are preferred over point clouds for a shared KITTI stem. ZIPs may wrap annotations and media in directory trees. Upload annotation and media archives through their respective fields. An import containing duplicate sample names is rejected to avoid accidental merging.

Malformed documents return useful errors and are rolled back. Invalid individual shapes/lines are skipped with warnings. Empty sample sets are rejected; samples with zero valid annotations remain and display a warning.

## Architecture and persistence

```text
frontend/src/          React + TypeScript, Vite, Tailwind, Recharts, Lucide
backend/app/database/ SQLAlchemy engine/session and additive migration
backend/app/models/   SQLite entities and relationships
backend/app/schemas/  Pydantic configuration/request validation
backend/app/parsers/  BaseAnnotationParser and four format strategies
backend/app/analyzers/ BaseDifficultyAnalyzer and four task strategies
backend/app/services/ Import, media matching, scoring, sampling, balancing
backend/app/routers/  REST workflow and exports
backend/tests/        Isolated pytest and browser fixtures
uploads/              User files, ignored by Git
exports/              Generated CSVs, ignored by Git
HANDOFF.md            Verified state and continuation instructions
```

SQLite stores datasets, samples, flexible JSON annotations, detailed analyses, settings, sampling runs/selections, reviewers and assignments. Review status/note are stored on the assignment as a one-to-one review result, avoiding an extra table for the same lifecycle. Restarting the backend preserves data. Deleting a dataset cascades its records and removes its uploaded folder. CSV files can be regenerated; older exported files are not automatically deleted.

Optional environment variables: `DATABASE_URL`, `UPLOAD_DIR`, `EXPORT_DIR` and frontend dev `API_PROXY_TARGET`. No secrets are needed.

## Difficulty formulas

All normalized feature values lie in [0,1]. Each feature records `value`, `raw`, `available`, `reason_if_unavailable`. Weighted scoring is `100 × sum(value × weight) / sum(available weights)`. Unavailable features are removed from both numerator and denominator; all unavailable gives an unavailable score. Settings validate the expected keys, finite nonnegative weights and a group sum of 1.

Visual defaults:

| Feature | Normalized heuristic | Weight |
| --- | --- | --- |
| Blur | `1 / (1 + variance_of_Laplacian / 100)` | .30 |
| Exposure | `abs(grayscale_mean - 127.5) / 127.5` | .25 |
| Low contrast | `1 - min(grayscale_std / 64, 1)` | .20 |
| Edge complexity | `min(Canny_edge_density / .2, 1)` | .15 |
| Entropy complexity | `grayscale_histogram_entropy / 8` | .10 |

Image analysis downsizes the longest side to at most 1600 pixels for CPU cost. Original annotation dimensions remain intact. Edge density and entropy are complexity heuristics; high values do not imply bad image quality.

Task defaults:

- BBox: count capped at 20 objects (.20), tiny fraction (.25), known occlusion fraction (.20), unique-pair IoU overlap fraction (.20), rare-label fraction (.15).
- Segmentation: count (.20), tiny polygon regions (.20), mean vertex-count complexity capped at 50 vertices (.25), bounding-envelope crowding proxy (.20), rare-label fraction (.15). Shoelace polygon area is used. Crowding is explicitly not polygon IoU. Source occlusion is shown as an informational metric.
- Keypoint: instance count (.20), missing fraction among known visibility (.25), occluded fraction among known visibility (.25), visible-pose envelope crowding (.15), rare-label fraction (.15). Unknown visibility is never assumed visible/missing. No articulated skeleton or inferred pose-quality metric is claimed.
- Cuboid: count (.20), known occlusion (.20), mean source truncation (.20), center pairs within five meters (.15), rare-label fraction (.15), sparsity (.10, unavailable until calibrated point analysis exists). Distance-to-sensor, projection quality and point density are unavailable and carry reasons.

Common defaults: tiny area ratio `< .01`; bbox/crowding IoU `> .30`; rare class frequency `< .05` of **all dataset annotations**. Count caps and fixed metric scales prevent one extreme sample from compressing the entire dataset. Pairwise metrics above 2,000 instances are explicitly unavailable to bound CPU cost.

Mixed samples analyze each task independently, then take an annotation-count-weighted mean of available task scores. Overall defaults are 70% annotation / 30% visual, renormalized if either source is unavailable. A measured empty annotation list has annotation difficulty 0; it is not missing annotation data. Scores are clamped to [0,100]: EASY <40, MEDIUM <70, HARD >=70. Exact weighted feature contributions are persisted and displayed. No random scoring or correctness probability is used.

Settings expose all task/visual/overall weight groups and thresholds. Saving atomically recalculates all datasets. Recalculation increments a dataset revision; prior sampling/assignments are marked **Needs Regeneration**. Old human reviews are retained and included in review-results exports.

## QC planning and review

Default sampling: 10% budget, 40% seeded random coverage / 40% high difficulty / 20% measured rare-edge signals, seed 42. Percentage budgets round up; counts must be whole numbers; budgets are capped to dataset size. Largest-remainder quotas use stable strategy order for ties. Strategies select in coverage→difficulty→edge order with no duplicates. Empty buckets redistribute through seeded coverage with the explicit reason `coverage_fallback`.

Greedy workload balancing sorts selected samples by difficulty descending and assigns to the reviewer with least total difficulty, then fewest samples, then stable reviewer ID. Only the latest QC subset is balanced. Unavailable overall difficulty is rejected instead of treated as zero effort. This heuristic balances effort but does not guarantee a globally optimal partition.

Each reviewer has an independent difficulty-ordered queue. No Issue stores REVIEWED; Issue Found stores ISSUE_FOUND; Skip stores SKIPPED. Notes are persisted. Next Priority Sample advances to another PENDING sample; skipped samples remain manually accessible. Saved reviews prevent destructive reviewer removal or rebalancing that subset. Generate a new subset to start a new planning run; historical results remain exportable.

CSV exports: `smart_sample.csv`, `review_assignments.csv`, `review_results.csv`. Exports use UTF-8 BOM for Excel, preserve unavailable scores as empty cells, and escape formula-like user text. Review results include historical runs; repeated samples may appear once per review run.

## REST API

Swagger is the authoritative request/response explorer.

| Route | Purpose |
| --- | --- |
| GET `/api/health` | Liveness |
| GET `/api/datasets`, GET/DELETE `/api/datasets/{id}` | Dataset list, health summary and deletion |
| POST `/api/datasets/upload` | Multipart annotations/media and synchronous analysis |
| GET `/api/datasets/{id}/samples`, `/api/samples/{id}`, `/api/samples/{id}/media` | Summaries, normalized details and original media |
| GET/PUT `/api/settings`, POST `/api/datasets/{id}/recalculate` | Configuration and recalculation |
| GET/POST `/api/datasets/{id}/sampling` | Latest QC subset and new run |
| GET/POST `/api/datasets/{id}/reviewers`, DELETE `/api/reviewers/{id}` | Human review team |
| POST `/api/datasets/{id}/balance`, GET `/api/datasets/{id}/assignments` | Workload and latest assignments |
| GET `/api/reviewers/{id}/queue`, PUT `/api/assignments/{id}/review` | Ordered queues, human statuses/notes |
| GET `/api/datasets/{id}/exports/{kind}` | CSV download and local export copy |

## Tests and build

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm run build
npm audit
```

Fixtures live only under `backend/tests`; pytest uses temporary SQLite/uploads/exports and removes them on completion. Tests cover parsers, validation, geometry, unavailable features, scoring/contributions, deterministic sampling, budget redistribution, balancing, upload matching, unsafe ZIP rejection, the full review/export lifecycle and stale planning revisions. Refer to HANDOFF.md for the latest executed counts and browser verification.

## Local MVP limits and future work

This is a local trusted-workspace tool without login, RBAC or internet deployment hardening. Import/analysis is synchronous. Large imports can take time; no background task scheduler is used. Limits: 512 MiB per upload group, 2 GiB expanded ZIP content and 10,000 extracted entries per group, 50,000 samples per import. The dataset browser paginates 20 rows in memory; it fetches all sample summaries. Full 3D visualization, calibrated sensor analysis, RLE rendering/metrics, CVAT video tracks, articulated pose skeletons and server-side pagination are future work.

Source dependencies and lockfile are committed; venv/node_modules/database/user media are not. Keep database and uploads together for backup. Read HANDOFF.md before continuing development on another machine.
