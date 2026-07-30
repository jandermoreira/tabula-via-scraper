# Cloud Firestore Database Specification (Tabula Via)

## Table of Contents

- [1. Data Standards](#1-data-standards)
- [2. Collection Hierarchy](#2-collection-hierarchy)
  - [Collection: `classes`](#collection-classes)
  - [Collection: `students`](#collection-students)
  - [Collection: `skills`](#collection-skills)
  - [Collection: `activities`](#collection-activities)
  - [Collection: `evidences`](#collection-evidences)

---

# 1. Data Standards

The database follows the conventions below.

## Identifiers (IDs)

- All primary keys are Strings containing either a UUID v4 or a unique identifier provided by Moodle.
- The document ID in the collection must be identical to the corresponding ID field stored inside the document.

## Date and Time

- Stored as Integer Numbers representing milliseconds since the Unix Epoch.

## Text and Enums

- Stored as Strings.
- Enum values are always uppercase.

---

# 2. Collection Hierarchy

Data is organized by user and by class.

## Base Path

```text
/users/{userEmail}/
```

`userEmail` is the email address of the user authenticated through Google OAuth. This ensures consistency across different clients (scraper and Android app) using the same authentication email.

---

## Collection: `classes`

Stores class information.

### Document ID

```text
{classId}
```

(UUID v4 or a unique identifier provided by Moodle)

### Fields

| Field            | Type    | Description                                       |
|------------------|---------|---------------------------------------------------|
| classId          | String  | Unique class identifier.                          |
| name             | String  | Course or class name.                             |
| academicYear     | String  | Academic year (e.g. `"2026"`).                    |
| period           | String  | Academic period/semester (e.g. `"1st Semester"`). |
| numberOfSessions | Number  | Total number of planned sessions.                 |
---

## Collection: `students`

Class subcollection.

Stores students associated with a specific class.

### Path

```text
/users/{userEmail}/classes/{classId}/students/
```

### Document ID

```text
{studentId}
```

(UUID v4 or a unique identifier provided by Moodle)

### Fields

| Field         | Type   | Description                                            |
|---------------|--------|--------------------------------------------------------|
| studentId     | String | Unique student identifier.                             |
| name          | String | Student's name.                                        |
| displayName   | String | Display name or preferred name.                        |
| studentNumber | String | Institutional student number.                          |
| classId       | String | Reference to the parent class.                         |
| status        | String | Possible values: `ACTIVE`, `INACTIVE`, or `CANCELLED`. |

---

## Collection: `skills`

Class subcollection.

Stores assessment criteria defined for the class.

### Path

```text
/users/{userEmail}/classes/{classId}/skills/
```

### Document ID

```text
{skillId}
```

(UUID v4 or a unique identifier provided by Moodle)

### Fields

| Field       | Type   | Description                                       |
|-------------|--------|---------------------------------------------------|
| skillId     | String | Unique skill identifier.                          |
| name        | String | Name of the assessed competency.                  |
| description | String | Detailed description of the assessment criterion. |
| classId     | String | Reference to the parent class.                    |

---

## Collection: `activities`

Class subcollection.

Stores records of activities or class sessions.

### Path

```text
/users/{userEmail}/classes/{classId}/activities/
```

### Document ID

```text
{activityId}
```

(UUID v4 or a unique identifier provided by Moodle)

### Fields

| Field       | Type   | Description                                  |
|-------------|--------|----------------------------------------------|
| activityId  | String | Unique activity identifier.                  |
| name        | String | Activity or lesson title.                    |
| date        | Number | Activity date in milliseconds.               |
| description | String | Classification: `"Individual"` or `"Group"`. |
| classId     | String | Reference to the parent class.               |

---

## Collection: `evidences`

### Path

```text
/users/{userEmail}/classes/{classId}/evidences/{evidenceId}
```

### Document ID

```text
{evidenceId}
```

The document name must be the `evidenceId`.

### Fields

| Field      | Type   | Description                                                            |
|------------|--------|------------------------------------------------------------------------|
| evidenceId | String | Unique ID (UUID or Moodle ID).                                         |
| classId    | String | Class ID.                                                              |
| name       | String | Evidence source name (e.g. `"Conditional List"` or `"Exam 1"`).        |
| deadline   | Number | Submission deadline in milliseconds since the Unix Epoch.              |
| type       | String | `"MONITORING"` or `"CONSOLIDATION"`.                                   |
| scores     | Map    | Evidence scores for each student in the format `{ studentId: score }`. |

