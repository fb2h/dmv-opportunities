# DMV High School Opportunity Website: Data Schema Contract (English)

**Status: CURRENT CANONICAL CONTRACT**  
**Contract version: 2.3.0 · Date: 2026-09-08**

This contract governs collection, integration, website implementation, and automated refresh. It defines two connected data contracts: the **backend maintenance schema** and the **frontend display schema**, plus publication, transformation, and filtering rules. These logical structures do not require two separate physical databases.

This document is the single contract that people and agents should follow. It supersedes “Data Schema — Locked 2026-09-07,” `DMV_Opportunity_Project_Plan_v0.1.md`, and every earlier Data Contract version wherever they conflict. Earlier files are historical drafts, not implementation instructions.

Version 2.3 preserves the six-filter public design while correcting cross-variant matching, scope, and collector-template problems found during implementation review. Filter conditions must be satisfied by one specific offering; no “widest value” may combine incompatible variants. Silence about money remains recorded but is not converted into a claim of no fee or no pay. **Application materials are not filters, and programs supported only by past-cycle information are not displayed publicly.** Existing historical data must be retained, not deleted to fit this schema.

**Change history**

| Version | Status | Main change |
|---|---|---|
| 2.3.0 | Current | Corrected cross-variant filter matching; clarified work-opportunity scope and incidental fees; made `not_mentioned` non-assertive; added community service; aligned the collector template and removed stale filter references. |
| 2.2.0 | Superseded | Scope narrowed to work opportunities; OpportunityType reduced; Subject collapsed; opportunity type and application status removed from public filters. |
| 2.1.0 | Superseded | Rule precedence; `record_version` fixed to factual change only; splitting narrowed to cycle and dates; Cost removed from filters; silence-about-money rule; `routes[]`; conflict records; new enum values. |
| 2.0.0 | Superseded | Minimal public filters; separate Pay and Cost; Any semantics; English canonical file. |
| 1.1.0 | Superseded draft | Combined Cost and compensation filter. |
| 1.0.0 | Superseded draft | Initial two-schema contract. |

This is an implementation handoff contract. Producing it does not mean a database, website, or refresh service has been implemented or activated.

## 1. Confirmed product decisions

| ID | Confirmed rule |
|---|---|
| P01 / revised 2.3 | **This site lists workplace-based opportunities for high school students in DC, Maryland and Virginia — paid or unpaid — plus genuinely accessible online ones.** In scope are roles in which the student performs duties for, assists, observes, or trains within an organization: internships, apprenticeships, paid jobs, volunteer positions, research positions, job shadowing, and trainee or counselor roles with real duties. Job shadowing is an intentional exception to the ordinary work-duty test. Out of scope are programs primarily purchased for instruction or attendance: summer camps, classes, courses, dual enrollment, early college, magnet and academy programs, test prep, tutoring, enrichment, college fairs, information sessions, webinars, and leadership seminars. Tuition or a participation fee charged primarily for instruction makes an opportunity out of scope; incidental application, registration, uniform, transportation, meals, housing, or background-check costs do not automatically make an otherwise genuine workplace role out of scope. |
| P02 | Exclude standalone scholarships and competitions. Continue collecting fee waivers and financial assistance attached to an included program. |
| P24 | **Attending is not working, but helping operate an activity can be.** Being a camp counselor, junior counselor, counselor-in-training, exhibit guide, or program assistant is in scope only when the student has genuine assigned duties. Attending the same camp or program as a participant is out of scope. When a trainee role charges tuition primarily for instruction, P01 excludes it even if it also includes limited duties. |
| P25 | **The public filters are six:** distance from ZIP, participation format, field of interest, current grade, when offered, and pay. Opportunity type and application status are collected and displayed but are not filters — opportunity type because the distinction between similar work roles proved unreliable to assign, and application status because the deadline and status are shown on the card instead. |
| P03 | Initial breadth-first collection target: 400–600 records. Report unique programs, specific offerings, and published programs separately. Historical versions and duplicates must not inflate public opportunity counts. |
| P04 / Q1 | Show approximate straight-line miles from a representative location for the user's ZIP to the activity location, not driving distance or commute time. |
| P05 / Q2 | Look for the actual address. A confirmed activity campus may provide a labeled approximate location. An otherwise publishable opportunity may remain visible with “Location to be confirmed.” |
| P06 / Q3 | Show one card per program. Match specific cycles, sessions, locations, or routes before aggregating into program cards. |
| P07 / final Q4 revision | The user selects current grade. The site supplies the current school-year context and converts against each program's stated eligibility reference; school year is not an additional visible filter. |
| P08 / Q5 | Keep current opportunities with unknown conditions by default, separating “Matches selected conditions” from “Conditions to confirm.” A match does not claim complete eligibility. |
| P09 / revised Q6 | Essays, recommendation letters, transcripts, interviews, resumes, portfolios, and other application requirements are collected and shown in details only. None are filters. |
| P10 / revised 2.3 | Use one public money filter. **Pay:** Any, With pay, No pay. Cost is not a public filter. Required fees and fee uncertainty are still derived and shown clearly on the card and in details. The backend continues to store exact fees, compensation, assistance, and uncertainty separately, so restoring a Cost filter later requires no re-collection. |
| P11 / Q8 | When delivery mode is not restricted, retain a separate online group during distance filtering. Online opportunities must still satisfy other selected conditions. |
| P12 / Q9 | Residential opportunities remain subject to the distance limit. Housing does not create an exemption. |
| P13 / final Q10 revision | Age eligibility remains in the backend and may appear in details, but the public website has no age input or age filter. Do not collect a student's date of birth. |
| P14 / final Q11 revision | Preserve all historical cycles in the backend. Do not display an unannounced current cycle. Current cards and details use confirmed current-cycle dates, never historical dates as substitutes. |
| P15 | Officially announced opportunities may appear before applications open. An announced cycle with unpublished dates may show “To be announced” without invented dates. |
| P16 | The backend is the only maintained master. Frontend data is derived automatically; collectors do not maintain a second set of frontend facts. |
| P17 | Keep the public filters minimal. Do not provide keyword, city, county, age, schedule, housing, fee-assistance, citizenship, work-authorization, residence, school-restriction, application-material, or interview filters. Retain those facts in the backend and allow cleared facts to appear in program details. |
| P18 | Current-grade choices include grades 8, 9, 10, 11, and 12. Match a “rising ninth grader” through current grade 8 and the offering's `rising_fall` basis. |
| P19 | Every single-choice public filter has an unrestricted Any state. Any is a query state, never a stored program fact. Multi-select filters use no selection to mean any and provide Clear all rather than an Any checkbox. |
| P20 | **Rule precedence.** Where a rule in this contract is explicit, the rule governs. The preference for over-matching (P21) applies only where no rule covers the case, or where a rule is genuinely ambiguous. It never overrides an explicit rule. |
| P21 | **Over-match rather than under-match — catch-all only.** Where this contract is silent or ambiguous, prefer the interpretation that shows more results. A student who sees an extra program loses one click; a student who never sees a program loses the opportunity. Subordinate to P20. |
| P22 / revised 2.3 | **Filters must match one coherent offering.** Create separate offerings when cycle, session, application route, or any material filter/display fact differs. The frontend still aggregates matching offerings into one card per program. See Section 2. |
| P23 / revised 2.3 | **Silence about money is recorded, not converted into certainty.** `not_mentioned` means the relevant material was checked and did not state fee or pay information. It displays as “not stated” and does not match either affirmative Pay choice. See Section 6.3. |

Rules labeled D in Section 7 are proposed implementation defaults in this contract, not additional product choices represented as already selected by the owner.

## 2. Record units and responsibilities

| Entity | Meaning and identity |
|---|---|
| `program` | Stable program identity. A rename, changed URL, or additional source does not automatically create a new program. A shared host does not make two programs identical. |
| `offering` | A specific cycle, session, or eligibility/fee route of a program. `program_id` links the program; `offering_id` identifies the offering. |
| `source` | The identity of a webpage, PDF, formal email, application form, or update entry point. One source may support multiple programs. |
| `snapshot` | An actually retrieved version of a source. Preserve the original file or reviewable text, retrieval time, and fingerprint. |
| `evidence` | A verbatim excerpt from a snapshot, linked to the record, fields, and cycle it supports. |
| `revision` | An immutable revision of a program or offering that permits reconstruction of earlier facts, rather than retaining only the latest values. |
| `collector_program_submission` | One program-level collector work item, including candidate facts and its supporting sources, snapshots, evidence, conflicts, and coverage record. |
| `collection_batch` | One or more validated collector submissions assembled for integration. Integration owns canonical IDs, deduplication, merging, and publication states. |
| `public_catalog` | A public data snapshot generated for a release, containing only displayable offerings. |

**Splitting rule (revised in 2.3):** An offering must be a coherent unit that can be evaluated without borrowing facts from another variant.

**Always split** for a new annual cycle or a distinct session. Also split when an application route or any material fact used by a public filter differs, including grade eligibility, delivery mode, Pay, season, subject classification, or the applicable activity-location set. Split when materially different fees, eligibility, schedules, or application instructions would otherwise make the card or details misleading.

**Do not split** merely because one route has several deadline stages, such as nomination, priority, and final deadlines, when the application route, eligibility, session, and other material facts are otherwise the same. Store those dates in `application.deadlines[]`.

Alternative sites may remain in one offering only when the offering's dates, eligibility, Pay, delivery mode, and other material conditions are identical at those sites. Use `all_required` when attendance at multiple sites is mandatory. If site-specific dates or conditions differ materially, create separate offerings.

A shared application form is useful evidence that variants may belong together, but it never overrides the coherent-offering rule. A different application form normally means separate offerings. At query time, every selected condition must be satisfied by the same `offering_id`; only after matching may the frontend aggregate offerings into one program card.

One integration owner maintains stable program identities. Do not automatically merge solely by URL, similar name, or common host. Retain original IDs and trace mergers through import mappings.

## 3. Common encoding conventions

1. The code blocks use TypeScript type notation to define **JSON data structures**. They are not JSON instances and do not prescribe an implementation language. Every listed key is required; `| null` permits a null value and arrays may be empty. `Omit` reuses a structure with named fields removed. Collectors must not add unregistered canonical fields.
2. `null` means unknown or not applicable, not `0`, `false`, free, or unrestricted. An empty array means no encoded entries, not proof of no requirements. Use `false` only for an explicit absence of a requirement, and `0` letters only when none are explicitly required. `FieldIssue.reason` distinguishes not stated, unclear, conflicting, and not applicable.
3. IDs are stable strings, independent of mutable deadlines, URLs, or status. Candidates may use batch-local IDs; integration assigns global IDs and remaps evidence. `record_version` is an integer starting at 1 and increasing with revisions. **`record_version` increments only when factual content changes.** Publication state transitions — `review_status`, `release_state`, `published_at`, `withdrawn_at`, `display_until`, `decision_reason` — do not increment it and do not create a `RecordRevision`; they are recorded by the `Publication` block's own timestamps. A person correcting a fact increments the version; a person approving an unchanged record does not. Without this rule, publishing a record would advance its version past `reviewed_record_version` and immediately fail its own Section 7.1 gate.
4. `ISODate` is `YYYY-MM-DD`; `ISODateTime` includes an offset or `Z`; `SchoolYear` is `YYYY-YYYY`, with consecutive years. Times use `HH:MM:SS`; `time_zone` stores a known IANA zone. Do not invent an unstated cutoff time. Store ZIPs as strings.
5. For a day-precision `DateFact`, `date/year/month` must agree. For a known year and month, set `date=null` and retain the actual `year/month`. Preserve season-only information in the raw text. Resolve a year only with clear cycle context; never fill missing dates with the first or last day of a month or add a year. Separate tentative and confirmed dates.
6. Amounts and quantities are nonnegative numbers; ages, grades, capacities, and recommendation counts are integers. If both bounds exist, `min<=max`. Exact values have equal bounds; one-sided ranges leave the other bound null. Preserve currencies and units. Do not directly compare hourly wages with total stipends or assume a 4-point GPA scale.
7. Standard grade values are `K`, `1` through `12`, and `graduated`. Preserve all officially applicable values, while the website's audience remains high school students. Use the controlled subject enum in Section 4 and preserve source terms in `subject_terms_raw`. Unknown classification is an empty array with an issue — the catch-all values that once absorbed it were removed in 2.2. Assign subjects generously: a position that plausibly belongs to two fields carries both, because a wrongly narrow assignment hides the position from a student who would have wanted it.
8. `last_checked_at/retrieved_at` describe a check or retrieval; `last_verified_at` describes factual verification. A successful page load, changed copyright year, or URL containing 2029 is not verification of the current cycle.
9. Evidence `field_paths` are JSON Pointers relative to their target record, such as `/eligibility/age/min`. One excerpt may support several fields. Every evidence item must reference a reviewable snapshot. Remap candidate references to canonical record IDs during import.
10. Stable names and host information may carry forward with provenance. Cycle-dependent grade, age, fees, schedule, and application requirements must not silently carry into a new cycle. Leave unverified current-cycle values unknown and keep past values in historical offerings.

“Must check” requires an attempt and a recorded outcome, **not a non-null answer to a fact the source never published**. Retain source text and snapshots for later re-extraction to reduce repeated searching.

## 4. Shared factual fields

The definitions below are shared by backend and frontend to prevent divergent meanings. `ProgramFacts` describes program identity; `OfferingFacts` describes a particular cycle, session, or route. Researchers provide facts and raw text; integration adds geocoding, verification, and publication information.

The groups cover dates and time commitment, locations, eligibility, fees/pay/aid, application routes and materials, cycles, and classification. `summary` is a one-sentence description written for a student around age 15. Translating this contract does not change the website's content-language setting.

```typescript
type ID = string;
type ISODate = string;
type ISODateTime = string;
type SchoolYear = string;
type TriState = boolean | null;
type UnknownReason = "not_stated" | "unclear" | "conflicting" | "not_applicable";
type OpportunityType = "internship" | "research" | "volunteer" | "paid_job"
  | "apprenticeship" | "shadowing" | "trainee";
// 2.2: "career_program" and "summer_camp" removed — they described programs a student
// attends, which P01 now places out of scope. "trainee" covers counselor-in-training,
// exhibit guide and program-assistant roles that carry real duties.
type OrgType = "university" | "community_college" | "hospital" | "federal"
  | "state_gov" | "local_gov" | "school_district" | "school" | "nonprofit"
  | "museum" | "company" | "library" | "parks" | "other" | "unknown";
type Subject = "health_medicine" | "science_research" | "computing_technology"
  | "engineering_trades" | "environment_outdoors" | "business_law_government"
  | "arts_media_humanities" | "education_working_with_kids"
  | "community_service";
// 2.3: nine public field values. Merges: science_research <- math_science;
// engineering_trades <- engineering + skilled_trades;
// business_law_government <- business + law_policy;
// arts_media_humanities <- arts_media + humanities_social_science;
// education_working_with_kids <- education + sports_recreation.
// "multidisciplinary" and "other" are removed: they were escape hatches that carried
// no meaning. Terms describing a program's purpose rather than its field —
// college_prep, general_academics, test_prep, enrichment, leadership — are not
// subjects and are not recorded here; they survive in the description.
type DeliveryMode = "in_person" | "virtual" | "hybrid" | "unknown";
type HousingMode = "residential" | "commuter" | "optional" | "unknown";
type CurrentGrade = "8" | "9" | "10" | "11" | "12";
type SeasonFilter = "summer" | "school_year" | "year_round";
type DeliveryModeFilter = "in_person" | "virtual" | "hybrid";
type PayFilterChoice = "with_pay" | "no_pay";
type CostFilterChoice = "program_fee" | "no_program_fee";
type ApplicationStatus = "not_yet_open" | "open" | "closed"
  | "no_application" | "unknown";
type LifecycleStatus = "scheduled" | "in_progress" | "ended" | "cancelled" | "unknown";

interface DateFact {
  date: ISODate | null;
  year: number | null;
  month: number | null;
  time: string | null;
  time_zone: string | null;
  precision: "day" | "part_of_month" | "month" | "season" | "date_range" | "unknown";
  part: "early" | "mid" | "late" | null;
  range_start: ISODate | null;
  range_end: ISODate | null;
  certainty: "confirmed" | "tentative" | "unknown";
  raw: string | null;
}
interface Quantity {
  min: number | null;
  max: number | null;
  unit: "hour" | "day" | "week" | "month" | "session" | "total" | "other" | "unknown";
  raw: string | null;
}
interface Amount {
  min: number | null;
  max: number | null;
  currency: string | null;
  unit: "hour" | "day" | "week" | "month" | "session" | "total" | "other" | "unknown";
  raw: string | null;
}
interface LocationFacts {
  location_id: ID;
  venue_name: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  county_or_equivalent: string | null;
  state: string | null;
  zip: string | null;
  country: string | null;
  address_kind: "activity_site" | "confirmed_campus_approximation"
    | "organization_reference" | "to_be_assigned" | "not_published" | "unknown";
  address_evidenced: boolean | null;
  raw: string | null;
}
interface Geocode {
  latitude: number | null;
  longitude: number | null;
  precision: "rooftop" | "parcel" | "street" | "postal_area" | "locality" | "unknown";
  provider: string | null;
  input_address: string | null;
  geocoded_at: ISODateTime | null;
  status: "verified" | "needs_review" | "failed" | "not_attempted";
}
interface Location extends LocationFacts { geocode: Geocode; }
interface Restriction {
  status: "unrestricted" | "restricted" | "conditional" | "unknown";
  values: string[];
  raw: string | null;
}
interface Area {
  kind: "country" | "state" | "county_or_equivalent" | "city" | "zip" | "other";
  name: string;
  state: string | null;
  country: string | null;
}
interface Eligibility {
  grades: {
    values: string[];
    basis: "application_date" | "application_deadline" | "program_start"
      | "rising_fall" | "specified_school_year" | "specified_date"
      | "not_grade_based" | "unknown";
    school_year: SchoolYear | null;
    as_of_date: ISODate | null;
    raw: string | null;
  };
  age: {
    min: number | null;
    max: number | null;
    basis: "application_date" | "application_deadline" | "program_start"
      | "specified_date" | "unknown";
    as_of_date: ISODate | null;
    raw: string | null;
  };
  citizenship: Restriction;
  work_authorization: Restriction;
  residency: {
    status: "unrestricted" | "restricted" | "conditional" | "unknown";
    areas: Area[];
    radius_miles: number | null;
    radius_anchor_raw: string | null;
    raw: string | null;
  };
  school: {
    status: "unrestricted" | "restricted" | "conditional" | "unknown";
    eligible_schools: string[];
    eligible_districts: string[];
    raw: string | null;
  };
  gpa: { min: number | null; scale: number | null; raw: string | null; };
  prerequisites_raw: string | null;
  other_conditions: Array<{
    effect: "required" | "preferred" | "aid_only" | "unknown";
    raw: string;
  }>;
  logic: "simple_and" | "complex" | "unknown";
  eligibility_raw: string | null;
}
interface Costs {
  fee_status: "none" | "not_mentioned" | "required" | "conditional" | "unknown";
  fees: Array<{
    kind: "tuition" | "application" | "registration" | "housing"
      | "meals" | "transport" | "supplies" | "other";
    amount: Amount;
    mandatory: TriState;
    refundable: TriState;
    applies_to_balance: TriState;
    amount_is_floor: TriState;
    conditions_raw: string | null;
  }>;
  compensation_status: "provided" | "not_mentioned" | "none" | "conditional" | "unknown";
  compensation: Array<{
    kind: "wage" | "stipend" | "reimbursement" | "other";
    amount: Amount;
    guaranteed: TriState;
    conditions_raw: string | null;
  }>;
  aid_status: "available" | "unavailable" | "conditional" | "unknown";
  aid_conditions_raw: string | null;
  additional_costs_raw: string | null;
  cost_raw: string | null;
}
interface Requirement {
  kind: "essay" | "recommendation_letter" | "transcript" | "interview"
    | "resume" | "portfolio" | "parent_consent" | "other";
  required: TriState;
  min_count: number | null;
  max_count: number | null;
  stage: "initial_application" | "selection" | "after_acceptance" | "multiple" | "unknown";
  conditions_raw: string | null;
  raw: string | null;
}
interface Deadline {
  deadline_id: ID;
  kind: "nomination" | "priority" | "final" | "aid" | "registration" | "other";
  due: DateFact;
  required_for_route: TriState;
  closes_entry: TriState;
  audience_raw: string | null;
  raw: string | null;
}
interface Application {
  route_type: "direct" | "school_nomination" | "referral" | "registration" | "other" | "unknown";
  route_name: string | null;
  application_url: string | null;
  instructions_raw: string | null;
  window_kind: "fixed" | "rolling" | "multiple_rounds" | "none" | "unknown";
  selection_method: "first_come" | "competitive" | "lottery"
    | "rolling_until_full" | "open_enrollment" | "host_selects" | "unknown";
  // "lottery" and "first_come" are not interchangeable and must not be guessed:
  // telling students to register the moment a lottery opens gives them an advantage
  // that does not exist. "host_selects" covers a decentralised model where individual
  // supervisors choose their own students and there is no central selection.
  reported_status: ApplicationStatus;
  opens: DateFact;
  deadlines: Deadline[];
  requirements: Requirement[];
  requirements_raw: string | null;
}
interface ProgramFacts {
  name: string;
  aliases: string[];
  organization: {
    name: string;
    org_type: OrgType;
    website_url: string | null;
    host_state: string | null;
  };
  program_url: string | null;
  program_status: "active" | "paused" | "discontinued" | "unknown";
  recurrence: "annual" | "multiple_per_year" | "continuous" | "one_time" | "unknown";
}
interface OfferingFacts {
  offering_name: string | null;
  cycle: {
    kind: "annual" | "academic_year" | "session" | "continuous" | "unknown";
    label: string | null;
    announcement_state: "announced" | "unannounced" | "unclear";
  };
  summary: string | null;
  opportunity_types: OpportunityType[];
  subjects: Subject[];
  subject_terms_raw: string[];
  season: "summer" | "school_year" | "both" | "year_round" | "other" | "unknown";
  delivery_mode: DeliveryMode;
  housing_mode: HousingMode;
  locations: LocationFacts[];
  location_relation: "single" | "alternatives" | "all_required" | "unknown";
  eligibility: Eligibility;
  costs: Costs;
  schedule: {
    start: DateFact;
    end: DateFact;
    duration: Quantity;
    hours_per_week: { min: number | null; max: number | null; raw: string | null; };
    schedule_raw: string | null;
    attendance_raw: string | null;
  };
  application: Application;
  reported_lifecycle: LifecycleStatus;
  capacity: number | null;
  selectivity_raw: string | null;
  transportation_raw: string | null;
  housing_raw: string | null;
  public_notes: string | null;
}
```

## 5. Backend maintenance schema and collector submission format

The backend holds complete facts, historical revisions, sources, candidates, coverage tasks, and publication controls. A collector may submit one `CollectorProgramSubmission` per program; the batch assembler converts one or more of these into a `CollectionBatch`. Both are standard collection outputs and neither grants publication authority. `BackendStore` describes logical master data and does not require exporting every historical snapshot on every run.

A collection candidate needs at least one discovery source, identifiable program and host names, and an offering supported by source text or explicit issue records. Unidentified leads may remain coverage tasks; do not invent names. A historical cycle known to have been officially announced is still `announced`; whether it has ended is a separate lifecycle fact.

Official announcement evidence, verification results, and site publication state are separate. Verification applies to a specific `record_version`. Human edits also create revisions; automated extraction must not silently overwrite them.

Changed source bytes create a new snapshot without overwriting old snapshots. A repeated retrieval of unchanged content may reuse the snapshot and record a separate check result. Monitor pages, PDFs, and link sets separately. `archive_uri` is a recoverable backend reference, never part of public data.

```typescript
interface Source {
  source_id: ID;
  url: string | null;
  internal_ref: string | null;
  title: string | null;
  publisher: string | null;
  medium: "webpage" | "pdf" | "email" | "application_form" | "other";
  roles: Array<"discovery" | "program_detail" | "application" | "attachment" | "update_entry">;
  authority: "first_party" | "authorized_school" | "third_party" | "unknown";
  access: "public" | "restricted" | "internal";
  needs_browser: boolean | null;
}
interface Snapshot {
  snapshot_id: ID;
  source_id: ID;
  retrieved_at: ISODateTime;
  source_published_at: ISODateTime | null;
  archive_uri: string | null;
  extracted_text: string | null;
  content_sha256: string | null;
  hash_basis: "raw_bytes" | "normalized_extracted_text" | "none";
  extraction_method: "static_html" | "rendered_dom" | "pdf_text" | "ocr" | "email" | "operator_supplied";
  quality: "usable" | "partial" | "empty_shell" | "needs_review";
}
interface Evidence {
  evidence_id: ID;
  snapshot_id: ID;
  target_kind: "candidate_program" | "candidate_offering" | "program" | "offering";
  target_id: ID;
  field_paths: string[];
  cycle_label: string | null;
  quote: string;
  locator: string | null;
  public_use: "quote" | "summary_only" | "internal_only";
}
interface FieldIssue {
  target_kind: "candidate_program" | "candidate_offering" | "program" | "offering";
  target_id: ID;
  field_path: string;
  reason: UnknownReason;
  note: string | null;
  blocking_publication: boolean;
}
interface ConflictRecord {
  conflict_id: ID;
  target_kind: "candidate_program" | "candidate_offering" | "program" | "offering";
  target_id: ID;
  field_path: string;
  candidates: Array<{ value: unknown; source_id: ID; snapshot_id: ID; quote: string; asserted_at: ISODateTime; }>;
  resolution: "pending" | "resolved_to_candidate" | "unresolvable";
  resolved_to: number | null;
  resolved_by: "human" | "rule_engine" | null;
  resolved_at: ISODateTime | null;
  blocking_publication: boolean;
}
interface CollectionCoverage {
  source_ids_read: ID[];
  fee_information_linked: boolean | null;
  fee_source_ids_read: ID[];
  compensation_information_linked: boolean | null;
  compensation_source_ids_read: ID[];
  not_mentioned_field_paths: string[];
}
interface Audit {
  created_at: ISODateTime;
  updated_at: ISODateTime;
  last_verified_at: ISODateTime | null;
  record_version: number;
}
interface Publication {
  review_status: "pending" | "passed" | "needs_review" | "rejected";
  reviewed_at: ISODateTime | null;
  reviewer_kind: "rule_engine" | "human" | null;
  reviewed_record_version: number | null;
  public_content_status: "pending" | "cleared" | "blocked";
  release_state: "draft" | "published" | "withdrawn";
  published_record_version: number | null;
  published_at: ISODateTime | null;
  withdrawn_at: ISODateTime | null;
  review_due_at: ISODateTime | null;
  display_until: ISODateTime | null;
  decision_reason: string | null;
}
interface Program extends ProgramFacts { program_id: ID; audit: Audit; }
interface Offering extends Omit<OfferingFacts, "locations"> {
  offering_id: ID;
  program_id: ID;
  locations: Location[];
  announcement_evidence_ids: ID[];
  application_status: ApplicationStatus;
  lifecycle_status: LifecycleStatus;
  field_issues: FieldIssue[];
  publication: Publication;
  audit: Audit;
}
interface RecordRevision {
  revision_id: ID;
  entity_kind: "program" | "offering";
  entity_id: ID;
  record_version: number;
  saved_at: ISODateTime;
  actor_kind: "collector" | "importer" | "rule_engine" | "human";
  change_reason: string;
  record: Program | Offering;
  evidence_ids: ID[];
}
interface MonitorTarget {
  source_id: ID;
  enabled: boolean;
  check_interval_days: number;
  last_checked_at: ISODateTime | null;
  last_success_at: ISODateTime | null;
  next_check_at: ISODateTime | null;
  last_outcome: "changed" | "unchanged" | "failed" | "not_checked";
  last_content_sha256: string | null;
  last_link_set_sha256: string | null;
}
interface SourceLink {
  from_source_id: ID;
  to_source_id: ID;
  first_seen_at: ISODateTime;
  last_seen_at: ISODateTime;
}
interface CoverageTask {
  task_id: ID;
  region: string | null;
  organization_or_district: string | null;
  opportunity_types: OpportunityType[];
  discovery_channel: "public_web" | "school_email" | "manual_submission";
  query_or_source_ref: string;
  status: "pending" | "checked_found" | "checked_none" | "blocked" | "follow_up";
  checked_at: ISODateTime | null;
  next_check_at: ISODateTime | null;
  candidate_count: number;
  new_program_count: number;
  notes: string | null;
}
interface Candidate {
  candidate_id: ID;
  original_record_id: string | null;
  research_task_id: ID | null;
  proposed_program_id: ID | null;
  discovery_channel: "public_web" | "school_email" | "manual_submission";
  discovery_source_ids: ID[];
  program_facts: ProgramFacts;
  offerings: Array<{
    candidate_offering_id: ID;
    proposed_offering_id: ID | null;
    facts: OfferingFacts;
  }>;
  evidence_ids: ID[];
  field_issues: FieldIssue[];
  conflict_ids: ID[];
  collection_coverage: CollectionCoverage;
  possible_duplicates: string[];
  original_payload: unknown | null;
}
interface CollectorProgramSubmission extends Candidate {
  schema_version: "2.3.0";
  taxonomy_version: "2.1.0";
  submitted_at: ISODateTime;
  collector_id: string;
  sources: Source[];
  snapshots: Snapshot[];
  evidence: Evidence[];
  conflicts: ConflictRecord[];
}
interface CollectionBatch {
  schema_version: "2.3.0";
  taxonomy_version: "2.1.0";
  batch_id: ID;
  submitted_at: ISODateTime;
  collector_id: string;
  candidates: Candidate[];
  sources: Source[];
  snapshots: Snapshot[];
  evidence: Evidence[];
  conflicts: ConflictRecord[];
  discovered_links: SourceLink[];
  coverage_tasks: CoverageTask[];
}
interface ImportDecision {
  batch_id: ID;
  candidate_id: ID;
  status: "imported" | "needs_review" | "rejected";
  program_id: ID | null;
  offering_id_map: Array<{ candidate_offering_id: ID; offering_id: ID; }>;
  decided_at: ISODateTime;
  reason: string;
}
interface BackendStore {
  schema_version: "2.3.0";
  taxonomy_version: "2.1.0";
  programs: Program[];
  offerings: Offering[];
  sources: Source[];
  snapshots: Snapshot[];
  evidence: Evidence[];
  conflicts: ConflictRecord[];
  revisions: RecordRevision[];
  monitor_targets: MonitorTarget[];
  source_links: SourceLink[];
  coverage_tasks: CoverageTask[];
  collection_batches: CollectionBatch[];
  import_decisions: ImportDecision[];
}
```

### 5.1 Ownership and evidence requirements

| Owner | Responsibility |
|---|---|
| Collector | Facts, official quotations, sources, cycle attribution, unresolved issues, discovery entry points, and coverage results in `CollectorProgramSubmission` or `CollectionBatch`. |
| Integration | Deduplication, stable IDs, import mappings, taxonomy checks, factual conflict resolution, canonical revisions, and field-level evidence links. |
| Geocoding/calculation | Coordinates and precision, cycle/window statuses, public labels, and derived filter values. |
| Publication | Eligibility-to-publish checks, public-content review, verification of the current revision, release snapshots, and withdrawal synchronization. |

Non-null current-cycle announcement, material eligibility, fees, activity locations, dates, and application requirements must trace to applicable evidence. Unknown materials do not block publication; unresolved material conflicts marked `blocking_publication=true` do. Ordinary missing facts are marked unknown; publication must not require every field to be filled.

Keep `Source.authority` separate from `Source.access`. Formal host or authorized-school emails may provide first-party evidence and are not discarded because they are not public webpages. Third-party directories support discovery; verify material facts with first-party sources. Publish only cleared quotations or reviewed public summaries. Do not directly expose email bodies, recipients, internal references, or restricted links. Facts supported solely by `internal_only` evidence need publishable support or remain in the backend.

Every new `Snapshot` must have an `archive_uri` or reviewable `extracted_text`. Do not turn a paraphrase into an evidence quote. The program summary and `public_notes` may paraphrase without claiming to be quotations. `capacity` is the number of places; applicant counts remain raw text. Do not derive an acceptance rate without admissions counts.

## 6. Normalization of material facts

### 6.1 Location and distance

- Check for a full address for in-person and hybrid offerings. Missing address fields are permitted with an issue. Purely virtual offerings use empty `locations`; the host's state belongs in `organization.host_state`, not an activity-state field.
- `activity_site` means the actual activity location. `confirmed_campus_approximation` requires evidence that the activity occurs on that campus. Use `organization_reference` for a headquarters reference, which does not participate in activity-distance or county/city matching.
- Accurate geocoding does not prove that an address is the activity site. Default distance eligibility requires one of the first two address kinds, `geocode.status=verified`, and `rooftop/parcel/street` precision. Do not present ZIP or city centroids as precise program locations.
- Compute straight-line miles from the user's ZIP representative location to the activity coordinates and label the result “Approximately X miles from your ZIP area.” Distances are query-derived values, not canonical program facts.
- For alternative sites, at least one site must satisfy all location conditions together. For mandatory multiple sites, every required site must satisfy the distance condition; do not use only the nearest site. An unknown required site produces uncertainty; a known required site outside the radius produces a mismatch.
- Published offerings with unknown locations may appear in the physical group's “Conditions to confirm” area with null distance, never labeled “within 20 miles.” An unknown alternative cannot convert a known out-of-range site into a confirmed match.
- Purely virtual opportunities bypass distance, but still respect the selected delivery mode, grade, subject, season, and Pay conditions. Housing facts remain separate from delivery mode but are not filters; housing does not exempt a physical offering from distance.

### 6.2 Grade, age, and eligibility

- Interpret `grades.values` together with `grades.basis`. “Grade 10 in this school year” uses `specified_school_year` and the applicable school year. “Rising junior” uses `rising_fall` and `11`. Do not mix these conventions.
- The user supplies current grade and school year. Convert using normal annual progression only when cycle and reference are clear. An unclear summer-grade reference is uncertain, not an automatic increment of one grade.
- Preserve the program's minimum age, maximum age, reference event/date, and raw wording. The website does not collect a student's age or date of birth and does not use age as a filter; show the rule in details for the family to verify.
- Citizenship, work authorization, residence, and school attendance are four separate restrictions. An activity located in MD does not imply MD-only residency. `unrestricted` needs affirmative evidence; `unknown` must not display as unrestricted.
- Preserve cross-condition OR logic such as “county resident OR district student.” Set `logic=simple_and` only when conditions can safely be treated as independent AND requirements. Flag complex logic for confirmation in the first release rather than converting it to AND and excluding students.
- `preferred` and `aid_only` conditions are not universal eligibility gates. The site claims matches to selected conditions, not guaranteed overall eligibility.

### 6.3 Fees, compensation, and assistance

- `fee_status` describes payments required by the program for the offering, including mandatory application or registration fees. Record optional services and self-arranged transport separately; “no fee” does not claim zero living expenses.
- `none` requires an explicit statement that there is no fee. `not_mentioned` means the relevant current-cycle sources were read, they did not mention a fee, and no identified fee or tuition source remains unread. It displays as **“Fee not stated”** and is not converted to `none`. A linked-but-unread fees page is `unknown`, never `not_mentioned`. An unknown amount is not zero. Fees and wages may coexist. Reimbursement alone does not qualify as wages or a stipend.
- A fees page labelled only for a past cycle is not evidence of a current fee. Record the figures on the historical offering, set the current offering's `fee_status` to `unknown`, and create a non-conflict field issue noting that current-cycle fees require verification. Create a `ConflictRecord` only when applicable sources assert incompatible facts for the same cycle.
- Apply the same evidence rule to compensation. `not_mentioned` displays as **“Pay not stated”** and does not become `none` or match the No pay filter. A linked compensation source that was not read is `unknown`.
- Record what was actually checked in `collection_coverage`: which source IDs were read, whether separate fee or compensation information was linked, which linked sources were read, and which field paths were checked and found silent. Without that record, *the page does not say* and *nobody looked* are indistinguishable.
- Assistance availability does not mean the student will attend free. Materially different fee or eligibility variants become separate offerings under Section 2. Unawarded conditional assistance remains conditional.
- Derive Pay and Cost independently within the same offering. Do not combine the distance, eligibility, fee, or Pay facts of different offerings. Retain and display assistance facts without using them as filters. Cost is not a public filter, but `cost_filter_value` is still derived for consistent display and possible future use.

### 6.4 Time, deadlines, and requirements

- Store cycle, activity schedule, application window, and deadline types separately. `annual` describes recurrence; `rolling` describes a window. Neither by itself means applications are currently accepted.
- Each deadline identifies its role, whether it is required for the route, and whether it closes entry. A priority deadline does not automatically close final applications. An aid deadline is not automatically the ordinary application deadline.
- Derive application status from official status, opening time, the actual entry route, and deadlines for required stages. Explicit closure overrides an apparently open window. A future deadline alone does not prove that applications have opened. Insufficient information yields `unknown`.
- Do not invent midnight when the cutoff time or zone is unknown. Show the date with “Confirm cutoff time” when relevant; do not promise an exact number of hours remaining.
- Distinguish explicitly unnecessary and unknown requirements, preserving stage and conditions. An interview after shortlisting is a selection-stage requirement. No materials or interviews appear in `SearchRequest`.
- Preserve time-commitment units. Do not silently convert days or months into weeks. For a weekly-hours range, all possible values must satisfy the user's limit for a confirmed match; partial overlap is uncertain.

## 7. Publication, refresh, and withdrawal contract

### 7.1 Publication gate

An offering may enter public data only when all conditions hold:

1. It is within P01–P02 scope and its program identity and offering attribution are resolved.
2. `cycle.announcement_state=announced`, with valid applicable evidence in `announcement_evidence_ids`. Cycle kind and label must be interpretable. A past cycle's announcement cannot announce a future cycle. Year-round rolling opportunities use `continuous` with a clear label, not a forced 2029 value.
3. `review_status=passed` and `reviewed_record_version` equals the factual revision being published. Verify cycle authenticity and material populated facts; ordinary unknown fields may remain unknown and visible as such.
4. `public_content_status=cleared`, with sources and content conforming to Section 5.1.
5. The program is not paused or discontinued, the offering is not cancelled or ended, no unresolved blocking conflict remains, and `display_until` has not passed if set.
6. Public output passes structural and reference checks; only then is the revision marked `published` and included in a release.

`release_state=published` alone is not proof that an offering remains displayable. Reapply lifecycle and expiry rules when generating and serving public data. If a program has no publishable offerings, generate no card, program-detail content, internal-search record, or sitemap entry. Historical records must not remain accessible through old detail URLs or public APIs.

### 7.2 Proposed implementation defaults

| ID | Default | Rationale and boundary |
|---|---|---|
| D01 | Keep a current offering after applications close and label it “Applications closed.” Withdraw it when the activity ends or is cancelled. | Closing and ending are different. Application status remains visible on the card even though it is not a filter. |
| D02 | Withdraw a version after its confirmed end date in the activity's local date. If the local zone is unknown, publication must assign an explicit `display_until` rather than inventing a precise local cutoff. | Avoid incorrect cross-year or cross-time-zone withdrawal. |
| D03 | For an unknown end date or continuous offering, schedule review 30 days after verification and expire display on day 90 unless actually reverified. | This is configurable maintenance policy, not an official activity-expiration claim. Fetch success does not renew it. Explicit cancellation or ending may withdraw it sooner. |
| D04 | Keep published offerings with unknown location or ordinary eligibility in “Conditions to confirm.” | Preserve possible opportunities without turning an unknown fact into a confirmed match. |
| D05 | If both physical and online versions of one program match, show one card in the physical group and include its matching online versions. Put it in the online group only when only online versions match. | Reconcile one-card-per-program with separate online grouping without duplicate cards. |

Keep these defaults in versioned publication/filter configuration, not in official facts that collectors must guess. Changing a default preserves source data and regenerates public output.

### 7.3 Incremental updates and consistency

- New cycle: create a new offering and keep past offerings and their sources. Never add one year to all historical records.
- Same-cycle change: create a revision and candidate change, verify the revision, then replace the public version. A still-valid prior published version may remain during ordinary review. Explicit cancellation, ending, or a material factual error requires immediate withdrawal rather than waiting in the ordinary review queue.
- Rechecking one field updates that field's evidence, not a claim that every fact was reverified. Public `last_verified_at` is the material-fact review time supporting this publication, not the time of a successful fetch.
- Generate a complete consistent snapshot with one `release_id`; switch public reads only after successful checks. On failure retain the previous successful release instead of publishing a partial batch. Expiry and withdrawal exclusions still apply to the previous release, so build failure does not prolong stale visibility.
- Synchronize withdrawal across lists, details, search indexes, and sitemaps. Public APIs read published data only; do not download the backend master to a browser and then hide its history client-side.
- Reassess deadline, end, and expiry boundaries at least daily. Read-time handling or scheduled work must apply an actual boundary when reached, without waiting for the official webpage to change. Cache validity must not cross the next status boundary without refresh.
- Retain recoverable backend data, snapshots, revisions, and successful public releases. The publication process records state changes without rewriting old revisions.

## 8. Frontend display schema

The frontend contains only displayable offerings and derived display/filter values. Cards and details use the same `PublicCatalog` facts, not separately maintained copies. `SearchRequest/SearchResult` describe query-time data, not a student-profile database. Do not write the user's ZIP or grade selection into the program master.

`PublicOffering` reuses shared facts but excludes candidates, internal source references, snapshots, review discussion, publication decisions, and historical versions. Virtual offerings have no invented physical activity address. `uncertainties` contains cleared user-facing explanations, not copied internal issue notes.

`public_sources` must contain at least one publicly accessible official program, application, or organization link. If only the host homepage is available, identify it as `role=organization`, not a current-cycle detail page. `public_evidence` contains only publishable quotations with public source URLs; do not force private email excerpts into it.

```typescript
interface PublicSource {
  url: string;
  title: string | null;
  publisher: string | null;
  role: "program_detail" | "application" | "attachment" | "organization";
  verified_at: ISODateTime;
}
interface PublicEvidence {
  field_paths: string[];
  cycle_label: string | null;
  quote: string;
  source_url: string;
  locator: string | null;
}
interface PublicLocation extends LocationFacts {
  latitude: number | null;
  longitude: number | null;
  geocode_precision: Geocode["precision"];
  distance_eligible: boolean;
  location_label: string;
}
interface PublicOffering extends Omit<OfferingFacts,
  "locations" | "reported_lifecycle" | "application" | "cycle"> {
  offering_id: ID;
  cycle: {
    kind: "annual" | "academic_year" | "session" | "continuous";
    label: string;
  };
  locations: PublicLocation[];
  application: Omit<Application, "reported_status">;
  application_status: ApplicationStatus;
  lifecycle_status: "scheduled" | "in_progress" | "unknown";
  pay_filter_value: PayFilterChoice | "unknown";
  cost_filter_value: CostFilterChoice | "unknown";
  primary_deadline_id: ID | null;
  public_sources: PublicSource[];
  public_evidence: PublicEvidence[];
  uncertainties: Array<{ field_path: string; reason: UnknownReason; label: string; }>;
  last_verified_at: ISODateTime;
  published_at: ISODateTime;
}
interface PublicProgram {
  program_id: ID;
  name: string;
  aliases: string[];
  organization: ProgramFacts["organization"];
  program_url: string | null;
  offerings: PublicOffering[];
}
interface PublicCatalog {
  schema_version: "2.3.0";
  taxonomy_version: "2.1.0";
  publication_policy_version: "2.3.0";
  release_id: ID;
  generated_at: ISODateTime;
  programs: PublicProgram[];
}
interface SearchRequest {
  reference_date: ISODate;
  user_zip: string | null;
  radius_miles: number | null;
  delivery_mode: DeliveryModeFilter | null;
  subjects: Subject[];
  season_value: SeasonFilter | null;
  current_grade: CurrentGrade | null;
  current_school_year: SchoolYear | null;
  pay_value: PayFilterChoice | null;
}
interface OfferingMatch {
  offering_id: ID;
  match_status: "confirmed_match" | "needs_confirmation";
  group: "physical" | "online";
  matched_location_ids: ID[];
  approximate_distance_miles: number | null;
  reasons: string[];
}
interface SearchResult {
  release_id: ID;
  evaluated_at: ISODateTime;
  query: SearchRequest;
  results: Array<{
    program_id: ID;
    card_group: "physical" | "online";
    match_status: "confirmed_match" | "needs_confirmation";
    offering_matches: OfferingMatch[];
  }>;
}
```

### 8.1 Publication transformation mapping

| Backend data | Frontend output | Transformation |
|---|---|---|
| Publishable `Program` and `Offering` revisions | `PublicProgram.offerings[]` | Select only versions passing Section 7 and group by `program_id`. Omit a program entirely when no offering remains. |
| Shared facts | Same-named public fields | Use verified current-cycle values and cleared public text; do not backfill from past cycles. |
| `Location.geocode` | Coordinates, precision, `distance_eligible` | Apply Section 6.1. Omit internal provider and processing records. |
| `costs.compensation_status` and applicable entries | `pay_filter_value` | provided with an explicit wage or guaranteed stipend→with_pay; explicit none/unpaid→no_pay; `not_mentioned`, conditional, varies, reimbursement-only, or unknown→unknown. |
| `costs.fee_status` and required fee entries | `cost_filter_value` | required participant fee→program_fee; explicit none→no_program_fee; `not_mentioned`, conditional, varies, or unknown→unknown. Optional housing, transport, meals, and refundable deposits do not automatically create program_fee. This value is for display consistency and possible future use, not a current filter. |
| `costs.aid_status` | No filter derivative | Retain in the backend and allow cleared detail display, but exclude it from `SearchRequest`. |
| Current `application.deadlines[]` | `primary_deadline_id` | Display only: prefer the nearest unexpired mandatory entry step, then the nearest relevant deadline. Show its type explicitly; use null when no reliable date exists. |
| Cycle, schedule, official application facts | `application_status/lifecycle_status` | Recalculate against actual time during generation and queries. A future date does not make expired, uncertain, or not-yet-open entry open. |
| Current public evidence and verification | `public_sources/public_evidence/last_verified_at` | Links, quotes, cycle, and fields must agree. Exclude internal references. |

When a source says only “February 2029,” retain month precision without inventing a day. Display multiple deadlines with their roles; do not provide a deadline-month filter. A deadline alone does not prove that applications are currently open.

## 9. Filtering behavior contract

**Rule precedence (P20).** Where a rule in this contract is explicit, the rule governs. The preference for over-matching stated below is a catch-all that applies only where no rule covers the case or where a rule is genuinely ambiguous. **It never overrides an explicit rule** — it does not, for example, relax the Section 7.1 publication gate, which is explicit.

**Over-matching preference (P21).** Where this contract is silent or ambiguous, choose the interpretation that shows more results. A student shown an extra program loses one click and can check the linked official page; a student never shown a program loses the opportunity. This means, for example, that an offering whose eligibility `logic` is `complex` is shown under “Conditions to confirm,” and two records that may or may not be the same program are both retained until a person confirms otherwise. It never permits facts from different offerings to be combined into one match.

**Order: apply publication eligibility, evaluate each offering, then aggregate program cards.** Multiple values within a filter use OR; different filters use AND. This UI rule does not rewrite complex OR logic in official eligibility conditions.

Every single-choice control has an **Any** state. Encode Any as `null`, not as an offering value. For the multi-select Field of interest control, an empty array means any field and the interface provides **Clear all**, not an Any checkbox. A missing ZIP/radius means any distance. `reference_date` and `current_school_year` are system-supplied evaluation context, not additional visible filters.

Each active condition returns `match / no_match / unknown`. Exclude an offering if any condition is a definite mismatch. All active conditions must match for `confirmed_match`; no definite mismatch with some uncertainty gives `needs_confirmation`. Including unknown conditions cannot bypass publication eligibility.

**Filter-specific rules override the general uncertainty rule.** Unknown Pay, including `not_mentioned`, does not match With pay or No pay because both selections make an affirmative claim. Unknown grade or location does not exclude an otherwise publishable offering; it appears under **Conditions to confirm**. Age is not a filter. These explicit rules take precedence over the over-matching preference.

| Website filter | Fields | Behavior |
|---|---|---|
| ZIP distance | User ZIP, radius, `locations` and coordinates | Approximate straight-line miles. No ZIP/radius means Any distance. Label campus approximations; identify unknown locations separately. |
| Participation format | `delivery_mode` | Any, In person, Virtual, or Hybrid. Hybrid has physical obligations and uses distance rules. |
| Field of interest | `subjects` | Controlled multi-select over nine values; no selection means any field. Assign generously — a position that plausibly belongs to two fields carries both, so either selection finds it. |
| Current grade | `eligibility.grades` plus current school-year context | Any, 8, 9, 10, 11, or 12. Convert against the grade reference; uncertain conversion requires confirmation. Current grade 8 can match a summer `rising_fall=9` opportunity. |
| When offered | `season` | Any, Summer, School year, or Year-round. Summer matches summer/both/year_round; School year matches school_year/both/year_round; Year-round matches year_round. |
| Pay | `pay_filter_value` | Any, With pay, or No pay. With pay requires an explicit wage or guaranteed stipend. No pay requires an explicit unpaid/no-compensation statement. `not_mentioned`, conditional, or genuinely unknown Pay does not match either selected value. |

Continue storing the following facts in the backend and allow them in details, but provide **no website filters** for them: keyword text, city/county, opportunity type, age, **cost and fee assistance**, application status, program dates and deadlines, time commitment, housing, citizenship, work authorization, residence, school/district restrictions, application materials, and interviews. Do not introduce hidden filter parameters for these facts. Required fees, fee uncertainty, the primary deadline, and application status must be shown clearly on the card rather than buried in details.

Additional constraints:

- An offering A that matches distance and offering B that matches Pay must not combine into one match. `offering_matches` must identify a single offering that satisfies all active filters and its qualifying sites.
- At most one card per program. Card fees, deadline, and distance must come from an identified matching offering. Show ranges or differences across multiple matches without synthesizing incompatible attributes into one label.
- “Conditions to confirm” does not mean historical-only information. Historical-only programs have already failed the publication gate.
- Selecting virtual-only excludes physical versions. Distance without a delivery-mode choice retains online results. An unknown delivery mode does not receive an automatic virtual distance exemption.
- Deadlines may support card display and default ordering. Use only relevant confirmed day-precision dates for exact ordering; put month-only and unknown dates in clearly labeled subsequent groups without inventing sortable days.

## 10. Collection, monitoring, and import workflow

1. **Receive existing work.** Preserve original JSON, Excel, CSV, references, and fields in `original_payload` or a traceable original file. Do not discard information merely to fit the new format.
2. **Discover broadly.** Use `CoverageTask` across regions, organizations, opportunity types, and channels. Record checked-with-no-results and blocked sources too. Counts are a coverage measure, not proof of completeness.
3. **Read first-party material.** Host webpages, formal PDFs, application forms, and authorized-school notices may support facts. Third-party lists supply leads. Collect past cycles into the backend without skipping them or assigning a future year.
4. **Submit candidates.** Submit one `CollectorProgramSubmission` per program or an assembled `CollectionBatch`. The batch assembler moves candidate facts and supporting sources, snapshots, evidence, and conflicts into the corresponding batch arrays without dropping `collection_coverage`, and validates all ID references. Collectors provide candidate facts, not `review_status=passed` or `release_state=published`. Unknown fields use null and issues; retain source text.
5. **Integrate centrally.** Validate structures, types, and references before deduplication, stable-ID mapping, and revision creation. Replaying the same `batch_id+candidate_id` must not create duplicates. Changed facts need a traceable new revision/batch, not silent mutation of the original batch.
6. **Verify and publish.** A rule engine may pass clear, conflict-free updates. Material conflicts, anomalous changes, and uncertain cycles go to a human queue. The owner need not manually confirm every record.
7. **Continue monitoring.** Check known programs and update entry points on configured schedules, increasing frequency near historically likely announcement periods. Historical patterns are monitoring priorities only.

Required change scenarios include overwritten webpage/PDF content at the same URL; an updated PDF with an unchanged parent page; a changed link target with unchanged visible text; new announcements, sections, and programs; scanned PDFs requiring OCR; and previously unknown hosts found by periodic broad discovery. Monitoring a fixed URL list does not replace new-source search.

A retrieval failure updates monitoring status; it does not prove cancellation, no fee, unrestricted eligibility, or nonrecurrence. Schedule a recheck and apply publication-validity policy to public data. Each run records sources checked, changes, new candidates, import outcomes, releases/withdrawals, and failures. These are internal operational records, not student-page content.

## 11. Example: refreshing for 2029

This is a fictional workflow example, not real program information. Assume a stable program ID of `example-research`:

| Event | Backend action | Website outcome |
|---|---|---|
| September 2028: only completed 2027 and 2028 information exists | Retain both historical offerings and source text; schedule checks | No program card and no invented “Expected in 2029” listing. |
| October 2028: the host announces a 2029 cycle without dates | Create `example-research-2029-main`, store announcement evidence, leave dates unknown | After verification and publication, show the 2029 opportunity with dates to be announced. |
| November 2028: the host announces opening on 2028-12-01 and closing on 2029-02-15 | Create a revision of the same 2029 offering with date evidence | Show not yet open and the current-cycle deadline. |
| December 1, 2028: applications actually open with supporting evidence | Update or derive open status | Show “Applications open” and the current deadline on the card. |
| February 2029: the host extends the deadline to March 1 | Preserve the February 15 revision, create and verify a March 1 revision, then publish | Display the currently effective March 1 deadline; February remains backend history only. |
| March 2029: applications close | Update closed status without deleting the record | Under D01, continue showing the current offering with “Applications closed.” |
| The 2029 activity ends | Mark ended and withdraw while retaining evidence and revisions | Remove the 2029 offering. If no other publishable offering exists, remove the whole program from public display. |
| The 2030 cycle remains unannounced | Use 2029 history to schedule monitoring; do not fabricate an announced 2030 offering | Do not relabel the 2029 listing and continue displaying it. |

A program may have multiple announced, unfinished cycles or sessions at the same time. Evaluate each offering separately rather than switching the whole database on January 1.

## 12. Migration from the original schema

| Original field/rule | New location | Migration action |
|---|---|---|
| `id` | `program_id` and `offering_id` | Resolve the record unit and preserve original-ID mappings. Do not assume every row is a unique program. |
| `name/org/org_type` | `ProgramFacts` | Normalize program and host identity. |
| `season/type/fields` | Offering `season/opportunity_types/subjects` | Use controlled enums and retain original subject text. Exclude standalone competitions and scholarships. |
| Single `location` | `locations[]/location_relation` | Split offerings by actual conditions; add address kind, county, and geocode precision. |
| `mode=residential` | `delivery_mode` plus `housing_mode` | Separate housing from physical delivery. |
| `cost_bucket/cost_usd/stipend_usd/comp_detail` | `costs` and derived frontend tags | Preserve units, fees, compensation, and aid separately. Missing amounts are not zero. |
| `grades/min_age/gpa_min` | `eligibility` | Add reference bases, maximum age, GPA scale, and source wording. |
| `citizenship/residency_req` | Separate identity, work authorization, residence, and school restrictions | Distinguish not stated from explicitly unrestricted and preserve complex AND/OR. |
| `duration/hours_per_week/program_dates_raw` | `schedule` | Keep structured numbers/ranges/units and raw text. |
| `app_opens/deadline_next` | Current `application.opens/deadlines[]` | Attribute to a cycle using evidence; a field name does not prove future validity. |
| `deadline_last` | Historical offering `deadlines[]` | Preserve its original cycle permanently; do not use it as a current public date or website filter. |
| `deadline_type=recurring_annual` | `program.recurrence` | Separate recurrence from fixed/rolling windows and deadline roles. |
| `cycle_status` | `cycle`, application/lifecycle state, and `publication` | Stop combining year, official announcement, application opening, and site publication into one state. |
| `requires` | `application.requirements[]` | Retain unknown/not-required semantics and stages; remove from all filter mappings. |
| `url/apply_url/quote/conf/last_verified` | Multiple sources, snapshots, field evidence, review, and verification time | Whole-record high/medium/low confidence does not replace evidence. Preserve original confidence in original_payload. |
| `notes` | `public_notes/FieldIssue/raw text` | Separate student guidance, internal issues, and source wording. |

For any earlier implementation, replace `cost_compensation_filter_value` with independently derived `pay_filter_value` and `cost_filter_value`. Only Pay remains a filter; Cost remains a display derivative. Remove `query`, opportunity type, city/county, age, Cost, application status, schedule, housing, assistance, and restriction parameters from `SearchRequest`; retain their underlying facts in backend/shared offering data. Treat removed query parameters as ignored during transition rather than deleting source facts.

When safe mapping is impossible, preserve the original and raise an issue. Do not manufacture certainty to increase the migration success rate.

## 13. Acceptance cases

These are required implementation behavior checks, not claims that a live website has been tested while writing this contract.

| ID | Input/scenario | Required result |
|---|---|---|
| A01 | Only a completed 2028 cycle exists; 2029 is unannounced | Retain in backend; exclude from public lists, details, and search. |
| A02 | A 2029 cycle is officially announced without dates | May publish “Dates to be announced”; do not substitute 2028 dates. |
| A03 | A 2029 cycle is announced but applications have not opened | May display `not_yet_open` and the known opening information; application status is not a filter. |
| A04 | A current grade 8 student filters summer opportunities; the source says “rising ninth grader” | Confirm a match when the reference is clear; grade 8 is a supported filter value. |
| A05 | A program requires age 16, but the website has no age filter | Preserve and display the age rule; do not hide the program or add an implicit age filter. |
| A06 | Letters are unstated; shortlisted applicants interview | Letters remain unknown and interview has a stage. No materials/interview filter exists. |
| A07 | Offering A is within 20 miles but unpaid; offering B is outside 20 miles but paid; select 20 miles plus Pay=With pay | No match may be constructed by combining the distance of A with the Pay of B. |
| A08 | Only a 20-mile limit is selected; an online offering satisfies other conditions | Retain in online group without a fake address or zero distance. |
| A09 | A residential offering is 50 miles away; select 20 miles | Exclude; no housing exemption. |
| A10 | Activity campus is confirmed but only an approximate campus address is available | Verified coordinates may support distance with an approximation label. A headquarters address does not qualify. |
| A11 | A current offering's activity site is unknown | May appear under conditions to confirm, with null distance and no within-radius claim. |
| A12 | Pay is unstated after applicable sources are checked | `compensation_status=not_mentioned`; display “Pay not stated.” It matches neither With pay nor No pay, but remains visible under Pay=Any. |
| A13 | An otherwise in-scope workplace role has a required incidental registration fee and possible assistance | `cost_filter_value=program_fee`; show the fee clearly. Details may show assistance. Neither Cost nor assistance is a filter. |
| A14 | Parent page is unchanged but a same-URL PDF is overwritten or its link target changes | Detect the change, create snapshots/evidence, and preserve previous content and cycles. |
| A15 | A webpage returns 404 or login fails | Record retrieval failure, not discontinuation; apply recheck/validity policy. |
| A16 | The same candidate batch is imported twice | No duplicate programs, offerings, or canonical revisions. |
| A17 | A same-cycle deadline moves from February to March | Preserve revisions; details expose only the currently effective March deadline. |
| A18 | Official eligibility says county resident OR district student | Preserve OR in the backend and details; do not convert to AND. No restriction filter exists. |
| A19 | The program recurs annually but current application status is unknown | recurrence=annual, application_status=unknown; do not automatically set open. |
| A20 | A release fails while some offerings reach their end time | No partial release. The previous successful release still excludes expired/withdrawn offerings. |
| A21 | One mandatory activity site is outside 20 miles | An all_required offering cannot pass using only the nearest site. |
| A22 | Physical and online versions of one program both match | Under D05 show one program card and preserve differences among matching offerings. |
| A23 | Only February 2029 is confirmed as the deadline, without a day | Display February 2029 without fabricating February 1 or 28. No month filter exists. |
| A24 | A program is cancelled or all public offerings have ended | Withdraw public records without deleting backend history or evidence. |
| A25 | A 2029 cycle is announced in fall 2028; a cross-school-year offering remains valid | Display by offering validity, not a current-calendar-year cutoff. |
| A26 | Pay=Any | Apply no restriction and include unknown values; never store Any on the offering. |
| A28 | One program has in-person and online variants with materially different conditions, even though one application form is shared | Create separate offerings; evaluate each separately and aggregate matching offerings into one program card. |
| A29 | One variant admits grades 10–12 and another admits grades 9–12 | Create separate offerings when other facts or instructions identify distinct variants; never store 9–12 as a synthetic widest range that is attributed to both. |
| A30 | Five sites are advertised as one session, but one has materially different activity dates | Create a separate offering for the different-date site; identical-site variants may remain together. |
| A31 | An offering is published, then withdrawn | `record_version` is unchanged by either transition; `reviewed_record_version` stays valid and no re-review is triggered. |
| A27 | No Field of interest is selected | Treat the empty array as any field; Clear all restores this state without an Any checkbox. |

Also check that all referenced IDs exist, evidence matches cycle and field, bounds are valid, published and reviewed versions agree, and public output contains no backend collections or internal source references.

## 14. Versioning and handoff

- This canonical contract, collector submissions, collection batches, and public data use `schema_version=2.3.0`; the taxonomy uses `taxonomy_version=2.1.0` because `community_service` was restored as a distinct public field, and the public release policy uses `publication_policy_version=2.3.0`.
- Changes to field meaning, enums, or filtering semantics require a contract version and changelog update. Replace this same canonical file so its identity and filename remain stable. One owner registers new canonical tags.
- Collectors deliver `CollectorProgramSubmission` files or an assembled `CollectionBatch`; integration delivers import decisions, master revisions, and unresolved issues; website implementation consumes `PublicCatalog` and `SearchRequest/SearchResult`; automation updates candidates through sources, links, snapshots, and coverage tasks. These responsibilities do not require simultaneously starting multiple agents.
- Calibrate the initial migration on 10–15 representative real records, including historical-only, announced/not-open, virtual, unknown-location, approximate-campus, materially different variants, rolling, cross-school-year, incidental-fee, and complex-eligibility cases. Continue broad collection without waiting for every marginal field to be complete.
- Report backend unique programs, historical/current offerings, published programs, unresolved records, checked sources, and coverage gaps separately. If too few current opportunities are publishable, expand discovery of announced opportunities instead of relaxing historical-display rules to meet a count.

**No blocking product questions remain.** D01–D05 are explicitly identified implementation defaults. Other collectors must follow this canonical contract rather than superseded drafts, historical-display rules, or removed frontend filters.
