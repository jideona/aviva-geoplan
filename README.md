# Aviva GeoPlan

AI-assisted GIS survey and fibre network planning platform.
Initial deployment: Wuye District, Abuja FCT.

Governed by `AVN-GEOPLAN-SRD-001` (requirements) and `AVN-GEOPLAN-SAD-001`
(architecture). Where this code and those documents diverge, the documents are
authoritative until formally amended.

---

## What is built

This repository contains the **Phase 1 vertical slice**: one complete path from
container start to a boundary rendered on a map, exercising every architectural
layer. It is production-quality code, not a mock-up.

| Capability | State |
|---|---|
| Docker stack — PostGIS, Redis, MinIO, API, frontend | Working |
| JWT authentication, Argon2id hashing, refresh tokens | Working |
| Role and permission model, enforced server-side | Working |
| Project creation with metric CRS validation | Working |
| Boundary upload — KML, KMZ, GeoJSON | Working |
| Geometry validation and repair, area measured in metric CRS | Working |
| Boundary versioning — supersede, never overwrite | Working |
| Append-only audit trail, enforced by database trigger | Working |
| Data source registry with licence class | Schema and seed only |
| Map workspace — boundary rendering, scale bar, coordinates | Working |
| Overture buildings import with provenance and licence class | Working |
| Street centreline import from KML/KMZ, street register | Working |
| Licence propagation and commercial-delivery position | Working |
| Protected writes — imports never overwrite field-verified records | Working |
| Building and street layers on the map, coloured by licence | Working |
| OSM road network import — named and unnamed | Working |
| Street assignment with confidence, reason and review queue | Working |
| Field naming worklist ranked by dependent buildings | Working |
| Street naming with source attribution and clearance report | Working |
| Data currency banding and staleness-ranked survey grid | Working |
| Field walkthrough pack export | Working |
| Route-analysis workbook import (recorded names, unit counts) | Working |
| Map-assisted street name matching | Working |
| Premises estimation model with sampling-bias gate | Working |
| Planning engine — serving zones and FAT placement | Working |
| Design panel: tune rules, zones on the map, utilisation | Working |
| Building register — filter, sort, paginate | Working |
| Branded Excel, CSV and GeoJSON export with attribution | Working |
| Export licence gating by purpose (internal / client / commercial) | Working |
| Survey, planning engine, optical, BOQ, AI detection | **Not built** |

Anything marked *Not built* is absent, not stubbed. There are no simulated
integrations presented as working (SRD NFR-MNT-006).

---

## Requirements

Docker Desktop. Nothing else — Node and Python run inside containers.

## Running it

```bash
make init
```

Open `infra/.env` and set three values before continuing:

- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `SEED_ADMIN_PASSWORD`

```bash
make up      # builds and starts everything; migrations run automatically
make seed    # in a second terminal
```

| Service | URL |
|---|---|
| Application | http://localhost:5173 |
| API documentation | http://localhost:8000/api/docs |
| MinIO console | http://localhost:9001 |

Sign in with the `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` you set.

```bash
make test    # run the test suite
make down    # stop, keep data
make reset   # stop and destroy all data
```

Data survives `make down` and a restart (SRD NFR-REL-005).

---

## Trying the slice end to end

1. Sign in.
2. **New project** — name it, district `Wuye`, leave the CRS at EPSG:32632.
3. Open the project.
4. **Upload boundary** — a KML, KMZ or GeoJSON polygon in EPSG:4326.
5. The boundary renders, the map fits to it, and the area appears in km²
   measured in the project metric CRS.

Worth deliberately trying: upload a GeoJSON whose coordinates are in UTM metres.
The system rejects it and tells you to reproject, rather than silently treating
metres as degrees.

---

## Architecture notes for whoever extends this

**Coordinate reference systems.** All geometry is stored in EPSG:4326. Every
measurement goes through `app.domain.crs`, which *refuses* to measure in 4326.
Area in degrees is a number with no meaning, and it is the easiest way to
corrupt a fibre design. Do not add a path that bypasses this.

**Layering.** `api → services → domain`, enforced by import-linter contracts in
`pyproject.toml`. The `domain` package performs no I/O and imports nothing from
the layers above it, so it is testable without a database.

**Audit is append-only in the database.** A trigger raises on UPDATE or DELETE
against `audit_log`. Application code cannot weaken this.

**Boundaries supersede rather than overwrite.** A new upload sets
`is_current = false` on the previous one, so any design stays traceable to the
extent it was produced under.

**Basemap.** Defaults to a plain engineering basemap. A licensed vector style
may be supplied via `VITE_BASEMAP_STYLE_URL`. Proprietary tiles must not be
scraped, bulk cached or treated as an imagery repository (SRD FR-GIS-016).

**Sample data is labelled.** The seeded Wuye project is marked as sample and
must never be represented as verified field data.

---

## Layout

```
backend/app/
  api/          FastAPI routers, dependencies, permission guards
  services/     use-case orchestration, transaction boundaries
  domain/       pure business logic — no I/O, no database
  db/           SQLAlchemy models, session, migrations
  core/         config, security, logging, permissions
frontend/src/
  api/          typed client with token refresh
  auth/         session context
  pages/        login, projects, project map
  components/   layout and shared UI
infra/          docker-compose, env template, postgres init
```

## Tests

19 tests covering identifier generation, the verification state model,
CRS measurement and boundary parsing.

The CRS tests are **spatial regression fixtures**: they assert known areas and
lengths for a square near Wuye. If a change makes those numbers move, the build
fails. That is deliberate — degree/metre confusion is silent otherwise.

## Wuye data — measured, not assumed

Against the actual Overture export for Wuye (`2026-06-17.0` release) clipped to
`Wuye District.kmz` (4.11 km²):

| | |
|---|---|
| Buildings inside the boundary | 3,597 |
| Discarded — outside boundary | 1,781 |
| Duplicate external ids | 0 |
| Google Open Buildings (attribution) | 1,858 |
| OpenStreetMap (share-alike) | 1,703 |
| Microsoft ML Buildings (share-alike) | 36 |
| **Share-alike share** | **48.3%** |

Two consequences that shape the build:

**Overture arrives already deduplicated.** No building carries more than one
source, and cross-source centroid containment is zero. Importing Google Open
Buildings separately would duplicate 1,858 buildings. The importer therefore
treats Overture as the single footprint load; conflation exists to reconcile
*survey* against it, not Overture against Google.

**Nearly half the geometry is share-alike.** A premises register delivered
commercially from this data may itself fall under ODbL. `licence_summary`
reports the position and the map colours buildings by licence class, so this
stays visible rather than surfacing during a client negotiation.

Attribute completeness in the same export: `num_floors` 2.2%, `height` 0.0%,
`names` 0.1%, `class` 1.9%. Overture supplies geometry. Everything that drives
the capital plan comes from survey.

### The road network is present; the names are not

From the raw OSM XML for the same boundary:

| | named | unnamed |
|---|---|---|
| Road segments | 17 | 420 |
| Length inside boundary | 10.9 km | 59.3 km |

This single fact determines the import design. Filtering OSM to named roads —
which both the Overpass GeoJSON and JSON exports do by default — discards 85%
of the network, and with it the ability to assign buildings at all:

| Buildings assignable at 60 m | |
|---|---|
| Against named roads only | 628 (17.5%) |
| Against the full network | 3,426 (95.2%) |

So `Street.name` is nullable, unnamed roads import as first-class records with
`needs_field_name = true`, and the naming queue ranks them by how many buildings
depend on them. 331 unnamed roads carry 2,808 buildings. That is a bounded
field task — drive the district naming roads — not a blocker.

**Always import raw OSM XML.** The importer rejects Overpass GeoJSON and JSON
exports with an explanation rather than a parse error, because this mistake
silently costs you the network.

## Pilot vs commercial: how the licence position is managed

The Wuye pilot is being built with street names read from a consumer mapping
product. That is a deliberate, time-boxed decision: it unblocks the pilot now,
and the licences are secured before anything is sold.

The architecture makes that decision reversible. Every street name records the
source it came from (`street.name_source`), and each source carries a licence
class and a commercial-ready flag:

| Source | Licence class | Commercial |
|---|---|---|
| Field observed / photographed | owned | yes |
| Authority register (AGIS/FCDA) | licensed_authority | yes |
| Local knowledge | owned | yes |
| Open data (OSM) | share_alike | no |
| Consumer map | desk_reference_restricted | **no** |

`GET /naming/clearance` reports whether the register could be delivered today
and, if not, exactly how many streets must be re-sourced. Because the names are
tagged at entry, re-sourcing is a filtered worklist rather than a re-survey of
the whole district.

**Licences can be secured later. Provenance cannot be reconstructed later.**
That asymmetry is the reason the tagging is not optional.

## Exports and the commercial gate

Every export declares a purpose, and the purpose determines what is permitted:

| Purpose | Wuye pilot today |
|---|---|
| `internal` | allowed |
| `client_review` | allowed |
| `commercial` | **blocked** — share-alike geometry and consumer-map street names |

A blocked export returns HTTP 451 with the specific reason and the remedy,
rather than producing a file that should not exist. Every permitted export
carries an attribution manifest naming each contributing source, its licence
and its feature count — in the CSV header, the GeoJSON `metadata` block and a
dedicated Excel sheet.

The Excel workbook has three sheets: a summary carrying the project, both CRS,
the filter applied and the caveats; the register itself with frozen headers and
autofilter; and sources and attribution.

## Data currency: what the register actually rests on

Measured against the Wuye load:

| Band | Buildings | |
|---|---|---|
| Current (under 1 yr) | 30 | 0.8% |
| Ageing (1–2 yr) | 1,512 | 42.0% |
| Stale (2–4 yr) | 1,895 | 52.7% |
| Obsolete (over 4 yr) | 160 | 4.4% |
| **Requiring field check** | **2,055** | **57.1%** |

Google Open Buildings was captured in May 2023 — 3.2 years old — and supplies
57% of the register. Wuye is still developing, so those records will be wrong
in a specific and predictable way: missing new build, and footprints altered
since capture.

The platform treats this as a routing problem rather than a caveat. Buildings
carry `source_update_date`, the map colours by currency band, and the survey
grid aggregates staleness into 250 m cells ranked for the walkthrough — 48
cells covering 2,075 buildings currently rank priority 1 or 2.

## Street naming: provisional codes, not borrowed names

Unnamed streets keep their provisional code (`WUY-ST-014`) until a surveyor
supplies a name. The code is stable and immutable, so assignment, exports and
design all work while the name is outstanding.

Consumer-map sourcing was considered and rejected: it would have made the
register unsellable without a re-survey, which is the one thing the provisional
code approach avoids entirely. The `proprietary_map` source remains in the
domain model so that any legacy data can be tagged and identified, but it is
not offered in the interface.

## The field walkthrough pack

`GET /walkthrough/pack.xlsx` produces the sheet a surveyor carries:

1. **Streets to name** — provisional code, road class, length, and how many
   buildings depend on it, with blank columns for the observed name, whether
   the sign was photographed, surveyor and date.
2. **Areas by priority** — 250 m cells ranked by data staleness, with centre
   coordinates.
3. **Currency bands** — what each band means and how hard to look.

The brief sheet states plainly that the register was built from open data,
where it will be wrong, and that recording serviceable units per building is
the objective — because that figure is what the capital plan rests on and no
data source provides it.

## Field survey data — what it supports and what it does not

The February 2025 Wuye walkthrough contributed 47 recorded street names with
measured lengths, and 450 buildings with directly observed unit counts.

### Street names cannot be matched by length

Five recorded streets are also named in OpenStreetMap, which gave a ground
truth to test against. Matching on length at ±10% identified the correct road
**uniquely in 0 of 5 cases**; the median recorded street has 9 candidate roads
at that tolerance, one has 30.

The measurements themselves are sound — median agreement with OSM is 3.3% —
but a single scalar cannot discriminate 47 names across 327 candidate roads.
`/street-matching` therefore ranks a shortlist by length and puts the decision
in front of a person with the map. Confirming a match writes the name with
`field_observed` provenance, which is licence-clean.

### The premises model, and why it refuses to give a district total

Fitted on all 450 observations:

| Band | n | Median | IQR | |
|---|---|---|---|---|
| 4–8 units (block) | 238 | 6 | 6–6 | well evidenced |
| 1 unit | 120 | 1 | 1–1 | well evidenced |
| 2–3 units | 53 | 2 | 2–2 | well evidenced |
| 9–15 units | 20 | 9 | 9–12 | thin sample |
| 16+ units | 19 | 30 | 20–40 | thin sample |

The six-unit block is the dominant Wuye form — 238 of 450 buildings.

`sampling_bias` compares the surveyed typology mix against the register's and
currently reports a 52.9 percentage-point divergence, because the survey walked
estates while the register is dominated by unclassified small structures.
`district_total` consequently returns `available: false`.

That refusal is the point. Multiplying the observed mean of 5.45 by the 3,597
buildings in the register yields roughly 19,600 premises — a number that looks
authoritative, would anchor a capital plan, and is not supported by the sample.
The model will produce a district figure once the survey covers the
under-sampled bands, and not before.

## Planning engine — stage 1

Capacitated clustering under a maximum drop length, then FAT siting on the
nearest suitable road. Pure domain code in `app/domain/planning/`, runnable
against fixtures without a database, deterministic on identifier so the same
input always yields the same design.

Against the 3,597 Wuye buildings, roughly one second per run:

| Config | FATs | Served | Unreachable | Longest drop |
|---|---|---|---|---|
| 1:16, 150 m | 330 | 3,571 | 26 | 149 m |
| 1:32, 150 m | 188 | 3,571 | 26 | 150 m |
| 1:32, 200 m | 174 | 3,584 | 13 | 199 m |
| 1:64, 200 m | 109 | 3,584 | 13 | 200 m |

### Two defects the real data exposed

**Drops exceeded their own limit.** Clustering measured distance from the
cluster seed, then the FAT moved to the road — pushing 163 zones past the
stated maximum. A repair pass now re-imposes the constraint after siting.

**Unreachable buildings sat inside breaching zones.** The first fix left them
in place with a warning. That is a false claim: a zone cannot serve a premises
600 m from its FAT at a 150 m drop limit. They now leave the design and appear
as unassigned. An unassigned building is a known gap; a breaching one is a lie
in a spreadsheet.

### The caveat on every number above

All 3,597 buildings were planned at one premises each, because none carry a
surveyed or modelled count. The engine warns on every run. With a median of six
units per building in the February survey, the real FAT requirement is likely
several times these figures — so treat them as a floor, not a design.

## Map labels and glyphs

MapLibre cannot render a symbol layer without PBF glyph ranges, and it fails
**silently** — no error, no warning, no text. That failure mode cost real time
during development, presenting first as "labels never appear" and later as
"labels appear briefly then vanish" (the second was a `minzoom` gated at the
same zoom the map opens at, so `fitBounds` switched them off).

Glyphs are therefore generated into `frontend/public/fonts` with `fontnik` and
served by the app itself. There is no external glyph dependency.

To regenerate, or to switch to the brand typeface once a TTF is licensed for
this use:

```bash
npm install fontnik
node scripts/generate-glyphs.js frontend/public/fonts
```

The directory name, the `text-font` value and the name recorded inside the PBF
must all agree. `VITE_GLYPHS_URL` overrides the location if the glyphs move
behind a CDN.

## Splitter architecture against real stock

Requested: FDH primary, FAT secondary, overall 1:32, no stock purchase. Those
cannot all hold. Every two-stage 1:32 is 1:4 × 1:8, and stock holds **zero
1:4 splitters** (78× 1:8, 18× 1:32). `app/domain/splitter_plan.py` computes the
fit for each architecture and reports the shortfall rather than assuming a buy:

| Architecture | Endpoints | From stock? |
|---|---|---|
| Single-stage 1:32 at FDH (FAT passive) | 512 | **Yes** — 16 active + 2 spare = stock of 18 |
| 1:4 × 1:8 two-stage 1:32 | 512 | No — buy 20× 1:4 |
| 1:8 × 1:8 two-stage 1:64 | 1024 | No — buy 102× 1:8 |

The zero-purchase path is single-stage 1:32, which drops the FAT-level split.
This is the confirmed architecture: the 1:32 splitter sits at the FDH, the FAT
is a passive drop terminal sized by physical port count (16 default).

### FDH tier and the pilot boundary

FATs cluster into FDH cabinets, each holding a splitter budget. With three
1:32 splitters per FDH — 96 premises each — the numbers fall out as:

| | |
|---|---|
| Splitters per FDH | 3 × 1:32 |
| Premises per FDH | 96 |
| **6-FDH pilot** | 18 splitters = full stock, **zero purchase**, 576 premises |
| Full district (1 premises/building) | 38 FDHs, 112 splitters |

So the 6-FDH arrangement is a genuine first phase covering ~16% of the district
from stock; expansion beyond it requires splitter procurement. The engine
reports the splitter gap on every run rather than assuming the buy.

## FAT coverage & property density report

`GET /projects/{id}/coverage` and `/coverage/report.xlsx` produce a per-FAT
breakdown of what each serving zone covers. Confirmed data (a building inside a
surveyed parcel with an observed unit count) and estimated data (type and units
inferred from footprint geometry) are reported **separately and never merged**.

Against the current Wuye design (188 FATs, 3,571 buildings):

| | |
|---|---|
| Confirmed buildings | 618 |
| Estimated buildings | 2,953 |
| Confirmed units | 2,233 |
| Estimated units (likely) | 5,447 (range 4,360–24,549) |
| FATs: confirmed / mixed / estimated | 14 / 33 / 141 |

Every FAT carries a coverage quality flag, a per-property-type breakdown, a
density figure and a confidence score. The wide estimated range is honest: 141
of 188 FATs rest entirely on footprint inference, and the report says so per
zone rather than presenting one blended number.

## Pre-connectorised underground stock — what it can build

The underground plant is plug-and-play: fixed-length, factory-terminated
cables that cannot be cut. `app/domain/connectorised.py` treats the design as a
constrained assignment — a cable serves a FAT only if its length reaches and
its ports suffice.

The stock:

| Terminal | Units | Drop ports | Lengths |
|---|---|---|---|
| 4-way | 3 | 12 | 200, 300 m |
| 8-way | 8 | 64 | 50–350 m |
| 12-way | 11 | 132 | 100–350 m |
| **FAT total** | **22** | **208** | |
| NOVUX 12pt feeder | 12 | — | 250–350 m |

What it achieves against the current design: **22 FATs deployed, 208 ports,
~181–208 premises**, using 7 of 18 splitters and leaving the 12 NOVUX feeders
for FDH interconnect. Zero purchase.

**The binding constraint is reach, not ports.** Cables top out at 350 m, so a
FAT must sit within roughly 260 m route (350 ÷ 1.35 duct factor) of its feed
point. The full-district design spreads FDHs ~2 km apart, which puts most FATs
out of reach — so this stock defines a *compact* pilot, a concentrated cluster
near the NOC, not a thin spread across Wuye. `GET /connectorised/fit` reports
the assignment, the leftover, and exactly why each unreachable FAT fails.

## Combined equipment envelope

The two stock sets — active splitters and passive connectorised terminals — are
complementary, not additive. The connectorised terminals draw splitter legs to
feed them; the 208-premises connectorised pilot already uses 7 of the 18 1:32
splitters. `GET /connectorised/envelope` reports the phased combined coverage:

Both phases share **one 16-port OLT** — the correction that matters. Phase 1
consumes PON ports before Phase 2 sees the rest, so they do not each get a full
OLT:

| Phase | Architecture | Premises | PON ports | Purchase |
|---|---|---|---|---|
| 1 — connectorised core | single-stage 1:32, passive FAT | 208 | 7 | **none** |
| 2 — conventional 1:32 | two-stage 1:4 × 1:8, spliced FAT | 288 | 9 | ~12× 1:4 + passive plant |
| **Combined (one OLT)** | | **496** | **16 / 16** | |

Reaching beyond 496 needs a **second OLT**, not more splitters — the 16-port
OLT is the ceiling, and the combined build fills it exactly. The 1:4 quantity
is ~12 (9 active + spares), not the 20 the BOM assumed: the BOM figure was for
an all-two-stage OLT with no connectorised carve-out. `GET /connectorised/
envelope` takes the OLT port count and accounts for the shared budget.

**Decision taken: procure 20× 1:4 PLC splitters.** It converts the Phase 2
extension from a 1:64 workaround into a proper two-stage 1:32, and the analysis
showed it is strictly better for roughly £100:

| | 1:64 (no 1:4) | 1:32 (buy 20× 1:4) |
|---|---|---|
| Premises | 512 | 512 |
| OLT PON ports used | 8 of 16 | 16 of 16 |
| Optical insertion | ~20.5 dB (tight) | ~17.5 dB (comfortable) |
| 1:8 consumed | 72 of 78 | 64 of 78 |

The 1:64 path used only half the OLT and ran a tight optical budget purely to
avoid a trivial spend. It is retained as a documented fallback. This also
matches the existing project BOM ("Procure 20 pcs" 1:4 PLC). The connectorised
core stays single-stage passive 1:32 — the pre-terminated FATs cannot host a
secondary splitter, so two-stage applies only to the conventional Phase 2 build.

## The buildable pilot

`GET /projects/{id}/pilot` and `/pilot/pack.xlsx` assemble the concrete pilot
from the current design: a connectorised core near the NOC plus a conventional
extension filling the OLT, with a splitter BOQ. Against the real Wuye data:

| | |
|---|---|
| OLT | 16-port, all 16 used |
| Phase 1 — connectorised | 11 FATs, ~116 premises, zero-splice |
| Phase 2 — conventional 1:32 | 37 FATs, ~384 premises, spliced |
| **Total pilot** | **~500 premises** |
| Beyond scope (future OLTs) | 282 FATs |

Splitter BOQ from a real run: 4× 1:32, 12× 1:4, 48× 1:8 — **all from stock,
zero to buy**, because the 20× 1:4 procurement decision is already reflected.
Connectorised cables consumed: nine 12-way and two 8-way assemblies. The pilot
pack lists the FAT schedule, the splitter BOQ and the connectorised cable usage
across four sheets.

The connectorised core lands smaller than 208 here (116) because the FATs near
the NOC are less dense than the district average, so fewer pre-terminated ports
are consumed close in — the conventional extension picks up the balance. Both
figures are honest outputs of the real geometry, not the theoretical envelope.

## Underground routing, phased

`GET /routing/phase/{1|2}` routes the pilot along the street graph: feeder
(NOC to FDH), distribution (FDH to FAT unioned into a duct-sharing tree),
trench length, chamber schedule and cable quantities with slack/jointing/
wastage/contingency allowances. A hand-rolled Dijkstra over 1,891 street nodes,
no pgRouting dependency.

Real Wuye numbers:

| | Phase 1 (connectorised, 11 FATs) | Phase 2 (conventional, 37 FATs) |
|---|---|---|
| Feeder NOC→FDH | 1,777 m | 9,831 m |
| Distribution trench | 1,261 m | 11,932 m |
| Duct sharing saved | 465 m | 4,388 m |
| Total trench | 3,038 m | 21,762 m |
| Handholes / manholes | 11 / 18 | 37 / 118 |

Duct-sharing is the point of the tree union: Phase 2's distribution legs sum to
16,320 m but share ducts down to 11,932 m of actual trench — 4.4 km not dug
twice, and not billed twice.

### Routing exposed a design flaw — and the fix closed it

Phase 1's feeder first came out at **1,777 m**, far beyond any feeder cable,
because FDHs were placed by district-wide clustering rather than by NOC
proximity. Two changes fixed it:

1. **NOC-anchored FDH placement** (`noc_anchored` in the design, "Pilot mode"
   in the panel) seeds FDH clusters from the head-end outward.
2. **The connectorised fit now measures real street routes**, not a
   straight-line estimate — a fixed cable either reaches along the duct or it
   does not.

With tight FDH clusters (250 m radius) the numbers close:

| | Before | After (pilot mode) |
|---|---|---|
| Feeder NOC→FDH | 1,777 m | **278 m** |
| Longest distribution leg | 1,044 m | **136 m** |
| Legs beyond 350 m cable reach | 4 | **0** |

Phase 1 now builds entirely on connectorised stock: a tight cluster at the
head-end, every distribution run within a pre-terminated cable's reach. The
loop is closed — routing feeds the cable fit, and the design responds.

## Cable routes on the map, and building numbering

Two additions make the routed design confirmable and BOQ-ready:

**Routes now connect to the plant.** The shortest path ends at the nearest
street node; a lateral stub is added from that node into each FDH cabinet, FAT
terminal and the NOC. The routes visually join the facilities, and `route_phase`
adds the lateral length to the trench and cable BOQ — short runs, but real ones
that a street-centreline route would otherwise miss.

**Buildings are numbered by serving FAT.** A design run assigns each building a
code carrying its FAT: `WUY-FAT-007-B03` is the third building on FAT-007,
sequenced in walk order. The map colours served buildings teal, labels the
building number at zoom 17.5+, and the popup names the serving FAT.
`GET /fat-schedule` lists every building each FAT serves with area, type and
unit count — the coverage-confirmation list a surveyor takes to the ground.

## Estate-aware FAT clustering

The generic clustering packs the nearest 12 buildings per FAT regardless of
estate lines, so a single estate scattered across several shared FATs — Metro
Estate's 20 buildings were split over 4 FATs, each also serving neighbours.

Buildings now carry a `group_id` (their parcel), and clustering fills an
estate's own FATs before pulling in neighbours. Metro Estate went from 4 shared
FATs to 2 — one pure, one holding the remainder plus a few neighbours to use
the ports. An estate is now a coherent unit in the design, which is also what a
construction crew and a sales campaign need.

Note on over-detection: Overture split Metro's 10 duplex rooftops into 20
footprints, so the footprint count coincidentally matched the 20 surveyed
units. Where a surveyed parcel exists, its observed unit count is authoritative
over the raw footprint count — applying "2 units per rooftop" on top of already-
split footprints would double-count.

## Map editing

An Edit toolbar (top-left, `gis:edit` permission) provides four tools:

- **Draw rooftop** — trace a building the import missed; click corners,
  double-click to finish. Records how it was captured, and the licence follows:
  traced over Esri imagery → `desk_reference_restricted` (pilot-only, must be
  re-sourced before sale); traced over owned drone or field-surveyed → owned.
  A rooftop digitised from display-only imagery is a derivative of it, so this
  is not a detail — it keeps the commercial-clean discipline intact.
- **Remove building** — click a non-serviceable building (shed, ruin,
  mis-detection) to exclude it. It vanishes from the map, register and design
  but the record and audit survive; it is reversible, unlike a hard delete of
  original data.
- **Move FDH/FAT** — drag a cabinet or terminal marker to reposition it; a FAT
  move locks the zone. Routes recompute on refresh.
- **Imagery date** — click anywhere to read the Esri World Imagery capture date
  under the cursor (its `SRC_DATE`), so you know how current a rooftop is before
  tracing it.

## Errors and guidance — two audiences

Failures are classified by who can act on them and routed accordingly.

**System faults (admin).** 5xx responses — schema behind, DB down, an
unhandled bug — return `kind: admin` with an operational remedy, are logged in
full with a request id, and surface as a red, persistent toast. The API also
logs `schema_behind` loudly at startup if migrations are pending, so a version
mismatch is caught at boot rather than as a mystery blank screen. `core/errors`
does the classification by HTTP status, so every existing `HTTPException` keeps
its message and gains an audience + remedy for free.

**Workflow mistakes (user).** 4xx responses — wrong file, missing prerequisite,
invalid value — return `kind: user` with the step to take, and show as an amber
auto-dismissing toast. The prerequisite messages already read as instructions
("Import buildings before running a design", "Upload a boundary before
importing parcels").

**Proactive guidance.** `GET /readiness` computes the pipeline state — boundary
→ roads → buildings → assignment → naming → design — marking each done, pending
or blocked, and naming the single next action. A "Next step" banner on the map
shows it, so a user is told what to do next before they hit an error, and a
blocked step names its prerequisite rather than failing opaquely.

## Next increment

1. Estate-to-building join, so the 450 observed unit counts land on real
   footprints and the design stops resting on an assumption of one premises
   per building.
2. Routing — feeder and distribution paths along the street graph, replacing
   straight-line drop measurement.
3. Walkthrough pack ingestion — accept the completed sheet back.
4. Background jobs — imports move to Celery before city-scale loads.
4. Row-level security in Postgres before multiple paying tenants share a
   deployment.
