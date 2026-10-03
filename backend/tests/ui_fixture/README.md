# Isolated browser verification fixture

`labels.xml` is a small CVAT mixed-task test fixture. It must never be uploaded to the production application on port 3000 or committed as a production dataset.

Browser verification on 2026-10-03 used a separate API on 8001, frontend on 3001 and `DATABASE_URL`, `UPLOAD_DIR`, `EXPORT_DIR` pointing inside this directory. It verified upload without media, computed dashboard data, a two-sample QC selection, reviewer addition, greedy balancing, priority navigation, Issue Found and No Issue, notes, and persistence after reload.

Generated SQLite databases, upload/export directories and logs are ignored by Git. A future session can reuse the XML in an isolated test database. Production fixtures are forbidden.
