# Technical Specification: Moodle Scraper → Firestore

## 1. Objective

Extract learning evidence (scores and deadlines) from Moodle and store it in Firestore.

---

# 2. Target Structure (Firestore)

The scraper must organize data into two levels:

* **Class Metadata (Timeline)**
* **Student Evidence**

## 2.1 Class Metadata (Timeline)

Stores information about each class activity.

**Path:**

```text
classes/{classId}/activities_metadata/{activityId}
```

### Fields

| Field      | Type      | Description                                                                       |
| ---------- | --------- | --------------------------------------------------------------------------------- |
| `title`    | String    | Activity name (e.g., "List 1", "Final Exam").                                     |
| `type`     | String    | `MONITORING` (lists, exercises, etc.) or `CONSOLIDATION` (exams, projects, etc.). |
| `deadline` | Timestamp | Activity submission date or scheduled date in Moodle.                             |

---

## 2.2 Student Evidence

Stores individual performance for each activity.

### Paths

**Monitoring**

```text
classes/{classId}/students/{studentId}/monitoring_evidence/{activityId}
```

**Consolidation**

```text
classes/{classId}/students/{studentId}/consolidation_evidence/{activityId}
```

### Fields

| Field   | Type          | Description                                                                                      |
| ------- | ------------- | ------------------------------------------------------------------------------------------------ |
| `score` | Number | null | Obtained score. Must be `null` when the activity was not completed or does not have a score yet. |

---

# 3. Extraction and Synchronization Logic

## 3.1 Activity Type Mapping

The scraper must classify each activity based on Moodle structure (for example, grade categories or activity name prefixes).

| Moodle Type                                            | Firestore Type  |
| ------------------------------------------------------ | --------------- |
| Process activities (quizzes, weekly assignments, etc.) | `MONITORING`    |
| Summative assessments (exams, tests, projects, etc.)   | `CONSOLIDATION` |

---

## 3.2 Missing Evidence Management

If a student is enrolled but does not have a record for an activity existing in `activities_metadata`, the scraper must create the corresponding document with:

```json
{
  "score": null
}
```

---

## 3.3 Frequency and Updates

The scraper must execute periodic synchronizations.

During each synchronization, it must:

* update the `score` field whenever the grade changes;
* preserve other existing data;
* remove activities from `activities_metadata` when they are deleted from Moodle.

---

# 4. Consistency Requirements

## 4.1 Unique IDs

The identifier `activityId` must be the same:

* in `activities_metadata`;
* in student evidence records.

---

## 4.2 Scope Management

The scraper must stop synchronizing students who:

* dropped the class;
* were removed from the class roster.

---

## 4.3 Timeline Ordering

The chronological order of activities must be determined exclusively by the `deadline` field stored in `activities_metadata`.

The scraper must not rely on alphabetical ordering of activity names.

---

# 5. Operational Flow

```text
1. Scan
   └── Reads the class grade structure from Moodle.

2. Sync Metadata
   └── Updates activities_metadata.

3. Sync Students
   ├── Updates monitoring_evidence.
   └── Updates consolidation_evidence.
```
